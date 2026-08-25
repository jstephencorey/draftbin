import asyncio
import hashlib
import logging
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import PurePosixPath

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from draftbin.config import Config, load_config
from draftbin.db import Database, Draft
from draftbin.html_document import document_title
from draftbin.ids import is_draft_id, new_draft_id
from draftbin.markdown_render import render_markdown
from draftbin.storage import HtmlStore
from draftbin.templates import (
    THEMES,
    render_landing,
    render_markdown_document,
    render_not_found,
)

logger = logging.getLogger("draftbin")

DRAFT_CSP = "; ".join(
    [
        "sandbox allow-popups allow-popups-to-escape-sandbox",
        "default-src 'none'",
        "style-src 'unsafe-inline'",
        "img-src https: data:",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    ]
)

PRIVATE_HEADERS = {
    "Cache-Control": "no-store, private, must-revalidate",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet",
}

DRAFT_HEADERS = {**PRIVATE_HEADERS, "Content-Security-Policy": DRAFT_CSP}


class HtmlUpload(BaseModel):
    html: str = Field(min_length=1)
    filename: str | None = None
    ttl_seconds: int | None = Field(default=None, gt=0)


class MarkdownUpload(BaseModel):
    markdown: str = Field(min_length=1)
    filename: str | None = None
    title: str | None = None
    theme: str | None = None
    ttl_seconds: int | None = Field(default=None, gt=0)


def safe_filename(value: str | None) -> str | None:
    if not value:
        return None
    name = PurePosixPath(value.replace("\\", "/")).name.strip()
    return name[:200] or None


def title_from_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    return PurePosixPath(filename).stem.strip() or None


def isoformat(epoch_seconds: int) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


def draft_summary(draft: Draft, config: Config, now: int) -> dict:
    return {
        "id": draft.id,
        "url": config.draft_url(draft.id),
        "title": draft.title,
        "filename": draft.filename,
        "source_format": draft.source_format,
        "theme": draft.theme or config.theme,
        "themeable": draft.source_format == "markdown",
        "size_bytes": draft.size_bytes,
        "created_at": isoformat(draft.created_at),
        "expires_at": isoformat(draft.expires_at),
        "expires_in_seconds": max(0, draft.expires_at - now),
    }


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()
    database = Database(config.db_path)
    store = HtmlStore(config.drafts_dir)

    def sweep_expired() -> int:
        expired_ids = database.take_expired_ids(int(time.time()))
        for draft_id in expired_ids:
            store.delete(draft_id)
        return len(expired_ids)

    def delete_orphaned_files() -> int:
        """Both delete paths drop the row first, so dying in between strands the file.

        Nothing would ever revisit it: sweeping is driven off rows, and this one's row
        is already gone. Reconciling against the table at startup is the only way back.
        """
        orphans = store.stored_ids() - database.all_ids()
        for draft_id in orphans:
            store.delete(draft_id)
        return len(orphans)

    async def sweep_forever() -> None:
        while True:
            await asyncio.sleep(config.sweep_interval_seconds)
            try:
                swept = await asyncio.to_thread(sweep_expired)
            except Exception:
                logger.exception("sweep failed")
                continue
            if swept:
                logger.info("swept expired drafts", extra={"count": swept})

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        database.initialize()
        store.initialize()
        store.discard_staged_writes()
        await asyncio.to_thread(sweep_expired)
        orphaned = await asyncio.to_thread(delete_orphaned_files)
        if orphaned:
            logger.warning("deleted orphaned draft files", extra={"count": orphaned})
        sweeper = asyncio.create_task(sweep_forever())
        try:
            yield
        finally:
            sweeper.cancel()

    app = FastAPI(title="draftbin", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def reject_oversized_bodies(request: Request, call_next):
        """FastAPI reads the whole request body before it solves dependencies.

        So `Depends(require_token)` cannot stop an anonymous caller making the server
        buffer a huge payload; only a check ahead of the route can. Content-Length is
        the sole size signal available that early, and a chunked upload does not carry
        one, so oversized documents are still caught again after rendering.
        """
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > config.max_upload_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "detail": (
                        f"Request body is {declared} bytes; the maximum is "
                        f"{config.max_upload_bytes}."
                    )
                },
            )
        return await call_next(request)

    @app.middleware("http")
    async def keep_responses_private(request: Request, call_next):
        """Nothing here is cacheable: API payloads and draft pages both carry secret URLs.

        Applied as middleware rather than per route so it also covers error responses,
        which are built fresh and would drop headers a route or dependency had set.
        """
        response = await call_next(request)
        for name, value in PRIVATE_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    app.state.config = config
    app.state.database = database
    app.state.store = store
    app.state.sweep_expired = sweep_expired

    def require_token(authorization: str | None = Header(default=None)) -> None:
        expected = f"Bearer {config.token}"
        if not authorization or not secrets.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="Invalid or missing API token.")

    def resolve_expiry(ttl_seconds: int | None, now: int) -> int:
        ttl = ttl_seconds or config.default_ttl_seconds
        if ttl > config.max_ttl_seconds:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"ttl_seconds {ttl} exceeds the server maximum "
                    f"{config.max_ttl_seconds}."
                ),
            )
        return now + ttl

    def resolve_theme(requested: str | None, draft_theme: str | None) -> str:
        if requested in THEMES:
            return requested
        return draft_theme or config.theme

    def publish(
        stored: str,
        served_bytes: int,
        title: str,
        filename: str | None,
        source_format: str,
        theme: str | None,
        expires_at: int,
        now: int,
    ) -> dict:
        if served_bytes > config.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Rendered document is {served_bytes} bytes; the maximum is "
                    f"{config.max_upload_bytes}."
                ),
            )

        draft = Draft(
            id=new_draft_id(),
            title=title,
            filename=filename,
            source_format=source_format,
            theme=theme,
            created_at=now,
            expires_at=expires_at,
            size_bytes=served_bytes,
            content_hash=f"sha256:{hashlib.sha256(stored.encode('utf-8')).hexdigest()}",
        )
        store.write(draft.id, stored)
        try:
            database.insert(draft)
        except Exception:
            store.delete(draft.id)
            raise
        return draft_summary(draft, config, now)

    @app.get("/", response_class=HTMLResponse)
    def landing() -> HTMLResponse:
        return HTMLResponse(
            render_landing(config.public_base_url, config.default_ttl_seconds, config.theme),
            headers=PRIVATE_HEADERS,
        )

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots() -> PlainTextResponse:
        return PlainTextResponse("User-agent: *\nDisallow: /\n")

    @app.post("/api/upload", status_code=201, dependencies=[Depends(require_token)])
    def upload_html(body: HtmlUpload) -> dict:
        now = int(time.time())
        filename = safe_filename(body.filename)
        return publish(
            stored=body.html,
            served_bytes=len(body.html.encode("utf-8")),
            title=document_title(body.html) or title_from_filename(filename) or "Untitled draft",
            filename=filename,
            source_format="html",
            theme=None,
            expires_at=resolve_expiry(body.ttl_seconds, now),
            now=now,
        )

    @app.post("/api/upload/markdown", status_code=201, dependencies=[Depends(require_token)])
    def upload_markdown(body: MarkdownUpload) -> dict:
        now = int(time.time())
        if body.theme is not None and body.theme not in THEMES:
            raise HTTPException(
                status_code=422, detail=f"theme must be one of {', '.join(THEMES)}."
            )

        expires_at = resolve_expiry(body.ttl_seconds, now)
        filename = safe_filename(body.filename)
        rendered = render_markdown(body.markdown)
        title = (
            (body.title or "").strip()
            or rendered.title
            or title_from_filename(filename)
            or "Untitled draft"
        )
        return publish(
            stored=rendered.html,
            # The auto palette carries both light and dark rules, so it bounds every theme.
            served_bytes=len(
                render_markdown_document(rendered.html, title, expires_at, "auto").encode("utf-8")
            ),
            title=title,
            filename=filename,
            source_format="markdown",
            theme=body.theme,
            expires_at=expires_at,
            now=now,
        )

    @app.get("/api/drafts", dependencies=[Depends(require_token)])
    def list_drafts() -> dict:
        now = int(time.time())
        return {"drafts": [draft_summary(draft, config, now) for draft in database.list_live(now)]}

    @app.delete("/api/drafts/{draft_id}", dependencies=[Depends(require_token)])
    def delete_draft(draft_id: str) -> dict:
        if not is_draft_id(draft_id) or not database.delete(draft_id):
            raise HTTPException(status_code=404, detail="Draft not found.")
        store.delete(draft_id)
        return {"ok": True}

    @app.api_route("/d/{draft_id}", methods=["GET", "HEAD"], response_class=HTMLResponse)
    def view_draft(draft_id: str, theme: str | None = None) -> HTMLResponse:
        now = int(time.time())
        draft = database.find_live(draft_id, now) if is_draft_id(draft_id) else None
        stored = store.read(draft.id) if draft else None
        if draft is None or stored is None:
            if draft:
                logger.error("draft row without stored body", extra={"draft_id": draft.id})
            return HTMLResponse(
                render_not_found(resolve_theme(theme, None)),
                status_code=404,
                headers=PRIVATE_HEADERS,
            )

        if draft.source_format == "html":
            return HTMLResponse(stored, headers=DRAFT_HEADERS)
        return HTMLResponse(
            render_markdown_document(
                stored, draft.title, draft.expires_at, resolve_theme(theme, draft.theme)
            ),
            headers=DRAFT_HEADERS,
        )

    return app
