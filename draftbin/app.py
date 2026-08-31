import asyncio
import hashlib
import logging
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo

from fastapi import Cookie, Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from pydantic import BaseModel, Field

from draftbin.config import Config, load_config
from draftbin.db import Database, Draft
from draftbin.fonts import FONT_CACHE_CONTROL, font_path
from draftbin.html_document import document_title
from draftbin.icons import ICO_ICON, ICON_CACHE_CONTROL, SVG_ICON, SVG_ICON_URL
from draftbin.ids import is_draft_id, new_draft_id
from draftbin.markdown_render import render_markdown
from draftbin.storage import HtmlStore
from draftbin.templates import (
    THEMES,
    IndexEntry,
    PasteForm,
    render_expired,
    render_index,
    render_landing,
    render_markdown_document,
    render_not_found,
    render_unlock,
)

logger = logging.getLogger("draftbin")

# Two words is a small enough keyspace that ids can collide, so give up rather than spin.
# Hitting this at single-user volumes would mean something is badly wrong.
ID_ATTEMPTS = 12

ACCESS_COOKIE = "draftbin_token"
ACCESS_COOKIE_MAX_AGE = 30 * 24 * 60 * 60


def draft_csp(public_base_url: str) -> str:
    return "; ".join(
        [
            "sandbox allow-popups allow-popups-to-escape-sandbox",
            "default-src 'none'",
            "style-src 'unsafe-inline'",
            # The sandbox directive puts the document on an opaque origin, and browsers
            # have not always agreed on whether 'self' still names this host afterwards.
            # Spelling the origin out removes the question.
            f"font-src 'self' {public_base_url}",
            # The tab icon is fetched under img-src, so the same reasoning applies to it.
            f"img-src 'self' {public_base_url} https: data:",
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


class ExpiryUpdate(BaseModel):
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


@dataclass(frozen=True)
class Prepared:
    """A document rendered and measured, before it is given an id, a created date, or a row."""

    stored: str
    served_bytes: int
    title: str
    filename: str | None
    source_format: str
    theme: str | None


def prepare_html(body: HtmlUpload) -> Prepared:
    filename = safe_filename(body.filename)
    return Prepared(
        stored=body.html,
        served_bytes=len(body.html.encode("utf-8")),
        title=document_title(body.html) or title_from_filename(filename) or "Untitled draft",
        filename=filename,
        source_format="html",
        theme=None,
    )


def prepare_markdown(body: MarkdownUpload, expires_at: int, zone: ZoneInfo) -> Prepared:
    if body.theme is not None and body.theme not in THEMES:
        raise HTTPException(status_code=422, detail=f"theme must be one of {', '.join(THEMES)}.")

    filename = safe_filename(body.filename)
    rendered = render_markdown(body.markdown)
    title = (
        (body.title or "").strip()
        or rendered.title
        or title_from_filename(filename)
        or "Untitled draft"
    )
    return Prepared(
        stored=rendered.html,
        # The auto palette carries both light and dark rules, so it bounds every theme.
        served_bytes=len(
            render_markdown_document(rendered.html, title, expires_at, "auto", zone).encode("utf-8")
        ),
        title=title,
        filename=filename,
        source_format="markdown",
        theme=body.theme,
    )


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
        "content_hash": draft.content_hash,
        "created_at": isoformat(draft.created_at),
        "expires_at": isoformat(draft.expires_at),
        "expires_in_seconds": max(0, draft.expires_at - now),
    }


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()
    database = Database(config.db_path)
    store = HtmlStore(config.drafts_dir)
    draft_headers = {**PRIVATE_HEADERS, "Content-Security-Policy": draft_csp(config.public_base_url)}

    def sweep_expired() -> int:
        now = int(time.time())
        expired_ids = database.take_expired_ids(now)
        for draft_id in expired_ids:
            store.delete(draft_id)
        database.purge_tombstones(now - config.tombstone_retention_seconds)
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

    def bearer_matches(authorization: str | None) -> bool:
        expected = f"Bearer {config.token}"
        return (
            bool(authorization)
            and authorization.isascii()
            and secrets.compare_digest(authorization, expected)
        )

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if not bearer_matches(authorization):
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

    def as_draft(draft_id: str, prepared: Prepared, expires_at: int, created_at: int) -> Draft:
        if prepared.served_bytes > config.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Rendered document is {prepared.served_bytes} bytes; the maximum is "
                    f"{config.max_upload_bytes}."
                ),
            )
        return Draft(
            id=draft_id,
            title=prepared.title,
            filename=prepared.filename,
            source_format=prepared.source_format,
            theme=prepared.theme,
            created_at=created_at,
            expires_at=expires_at,
            size_bytes=prepared.served_bytes,
            content_hash=f"sha256:{hashlib.sha256(prepared.stored.encode('utf-8')).hexdigest()}",
        )

    def allocate_draft_id() -> str:
        for _ in range(ID_ATTEMPTS):
            candidate = new_draft_id()
            if not database.id_in_use(candidate):
                return candidate
        raise HTTPException(status_code=503, detail="Could not find a free draft id.")

    def publish(prepared: Prepared, expires_at: int, now: int) -> dict:
        draft = as_draft(allocate_draft_id(), prepared, expires_at, now)
        store.write(draft.id, prepared.stored)
        try:
            database.insert(draft)
        except Exception:
            store.delete(draft.id)
            raise
        return draft_summary(draft, config, now)

    def token_matches(candidate: str | None) -> bool:
        """compare_digest raises on non-ASCII str, and a cookie is attacker-supplied on
        every read now, so a crafted one must be a refusal rather than a 500."""
        return (
            bool(candidate)
            and candidate.isascii()
            and secrets.compare_digest(candidate, config.token)
        )

    def reader_is_known(authorization: str | None, cookie: str | None) -> bool:
        return bearer_matches(authorization) or token_matches(cookie)

    def landing_page(form: PasteForm, status_code: int = 200) -> HTMLResponse:
        return HTMLResponse(
            render_landing(
                config.public_base_url, config.default_ttl_seconds, config.theme, form
            ),
            status_code=status_code,
            headers=PRIVATE_HEADERS,
        )

    def remember_token(response: Response) -> Response:
        """Only ever called once the token has been checked, so the cookie is the token."""
        response.set_cookie(
            ACCESS_COOKIE,
            config.token,
            max_age=ACCESS_COOKIE_MAX_AGE,
            path="/",
            httponly=True,
            # Lax rather than Strict, now that reading needs the cookie too: Strict would
            # withhold it when a draft link is clicked from another site, so an unlocked
            # device would still be asked for the token every time it arrived from Slack
            # or webmail. Lax rides along on top-level navigation but is still withheld on
            # cross-site POST, which is the request a hostile page would have to forge to
            # publish on Joseph's behalf.
            samesite="lax",
            secure=config.cookies_are_secure,
        )
        return response

    def unlock_page(action: str, error: str | None, status_code: int) -> HTMLResponse:
        """Carries PRIVATE_HEADERS and never draft_headers: the draft CSP sandboxes the
        document onto an opaque origin and sets form-action 'none', so a gate page served
        under it could not submit the very form that unlocks it."""
        return HTMLResponse(
            render_unlock(config.theme, action, error),
            status_code=status_code,
            headers=PRIVATE_HEADERS,
        )

    def unlock(action: str, token: str) -> Response:
        if not token_matches(token.strip()):
            return unlock_page(action, "That token was not accepted.", 401)
        return remember_token(RedirectResponse(action, status_code=303))

    @app.get("/", response_class=HTMLResponse)
    def landing(draftbin_token: str | None = Cookie(default=None)) -> HTMLResponse:
        return landing_page(PasteForm(needs_token=not token_matches(draftbin_token)))

    @app.post("/drafts")
    def unlock_index(token: str = Form(default="")) -> Response:
        return unlock("/drafts", token)

    @app.get("/drafts", response_class=HTMLResponse)
    def drafts_index(
        theme: str | None = None,
        authorization: str | None = Header(default=None),
        draftbin_token: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        """The reader-facing twin of GET /api/drafts, which still answers to a bearer."""
        if not reader_is_known(authorization, draftbin_token):
            return unlock_page("/drafts", None, 401)

        now = int(time.time())
        entries = [
            IndexEntry(
                id=draft.id,
                title=draft.title,
                created_at=draft.created_at,
                expires_at=draft.expires_at,
                size_bytes=draft.size_bytes,
            )
            for draft in database.list_live(now)
        ]
        return HTMLResponse(
            render_index(entries, resolve_theme(theme, None), config.display_zone),
            headers=PRIVATE_HEADERS,
        )

    @app.post("/paste")
    def paste_draft(
        text: str = Form(default=""),
        title: str = Form(default=""),
        token: str = Form(default=""),
        draftbin_token: str | None = Cookie(default=None),
    ) -> Response:
        """Publish straight from a browser, for the times there is no terminal to hand.

        A form cannot send a bearer header without JavaScript, and the CSP rules that out,
        so the token arrives in a field once and then rides in a cookie.
        """
        # Copying a token off a line picks up a trailing newline more often than not, and
        # "that token was not accepted" is a miserable way to find out. The cookie is set
        # by us and never needs it.
        entered = token.strip()
        supplied = entered or draftbin_token or ""
        if not token_matches(supplied):
            stale_cookie = not entered and draftbin_token is not None
            message = (
                "That token is no longer valid — it has probably been rotated. Enter the "
                "current one."
                if stale_cookie
                else "That token was not accepted."
            )
            response = landing_page(PasteForm(text, title, True, message), status_code=401)
            if stale_cookie:
                response.delete_cookie(ACCESS_COOKIE, path="/")
            return response

        if not text.strip():
            # The token was good, so remember it anyway rather than asking twice.
            return remember_token(
                landing_page(PasteForm(text, title, False, "Nothing to publish."), 422)
            )

        now = int(time.time())
        expires_at = resolve_expiry(None, now)
        prepared = prepare_markdown(
            MarkdownUpload(markdown=text, title=title.strip() or None),
            expires_at,
            config.display_zone,
        )
        draft = publish(prepared, expires_at, now)

        # Relative, so the address bar keeps whatever hostname the browser arrived on —
        # that is the one worth sharing from a phone.
        return remember_token(RedirectResponse(f"/d/{draft['id']}", status_code=303))

    @app.api_route("/static/fonts/{filename}", methods=["GET", "HEAD"])
    def font_file(filename: str) -> FileResponse:
        path = font_path(filename)
        if path is None:
            raise HTTPException(status_code=404, detail="Not found.")
        return FileResponse(
            path, media_type="font/woff2", headers={"Cache-Control": FONT_CACHE_CONTROL}
        )

    @app.api_route("/favicon.ico", methods=["GET", "HEAD"])
    def favicon() -> FileResponse:
        """Where a browser looks by itself, which is the only icon an HTML draft gets."""
        return FileResponse(
            ICO_ICON,
            media_type="image/x-icon",
            headers={"Cache-Control": ICON_CACHE_CONTROL},
        )

    @app.api_route(SVG_ICON_URL, methods=["GET", "HEAD"])
    def icon_svg() -> FileResponse:
        return FileResponse(
            SVG_ICON,
            media_type="image/svg+xml",
            headers={"Cache-Control": ICON_CACHE_CONTROL},
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
        return publish(prepare_html(body), resolve_expiry(body.ttl_seconds, now), now)

    @app.post("/api/upload/markdown", status_code=201, dependencies=[Depends(require_token)])
    def upload_markdown(body: MarkdownUpload) -> dict:
        now = int(time.time())
        expires_at = resolve_expiry(body.ttl_seconds, now)
        return publish(prepare_markdown(body, expires_at, config.display_zone), expires_at, now)

    def republish(existing: Draft, prepared: Prepared, expires_at: int, now: int) -> dict:
        draft = as_draft(existing.id, prepared, expires_at, existing.created_at)
        previous = store.read(draft.id)
        store.write(draft.id, prepared.stored)
        try:
            database.replace(draft)
        except Exception:
            if previous is not None:
                store.write(draft.id, previous)
            raise
        return draft_summary(draft, config, now)

    def require_live_draft(draft_id: str, now: int) -> Draft:
        """Expired ids are gone for good; reviving one would resurrect a link that leaked."""
        existing = database.find_live(draft_id, now) if is_draft_id(draft_id) else None
        if existing is None:
            raise HTTPException(status_code=404, detail="Draft not found.")
        return existing

    @app.put("/api/drafts/{draft_id}/html", dependencies=[Depends(require_token)])
    def replace_with_html(draft_id: str, body: HtmlUpload) -> dict:
        now = int(time.time())
        existing = require_live_draft(draft_id, now)
        return republish(existing, prepare_html(body), resolve_expiry(body.ttl_seconds, now), now)

    @app.put("/api/drafts/{draft_id}/markdown", dependencies=[Depends(require_token)])
    def replace_with_markdown(draft_id: str, body: MarkdownUpload) -> dict:
        now = int(time.time())
        existing = require_live_draft(draft_id, now)
        expires_at = resolve_expiry(body.ttl_seconds, now)
        prepared = prepare_markdown(body, expires_at, config.display_zone)
        return republish(existing, prepared, expires_at, now)

    @app.patch("/api/drafts/{draft_id}", dependencies=[Depends(require_token)])
    def extend_draft(draft_id: str, body: ExpiryUpdate) -> dict:
        """Buy more time on a draft you are still reading, without minting a new link."""
        now = int(time.time())
        existing = require_live_draft(draft_id, now)
        expires_at = resolve_expiry(body.ttl_seconds, now)
        database.set_expiry(existing.id, expires_at)
        return draft_summary(replace(existing, expires_at=expires_at), config, now)

    @app.get("/api/drafts", dependencies=[Depends(require_token)])
    def list_drafts() -> dict:
        now = int(time.time())
        return {"drafts": [draft_summary(draft, config, now) for draft in database.list_live(now)]}

    @app.delete("/api/drafts/{draft_id}", dependencies=[Depends(require_token)])
    def delete_draft(draft_id: str) -> dict:
        now = int(time.time())
        if not is_draft_id(draft_id) or not database.delete(draft_id, now):
            raise HTTPException(status_code=404, detail="Draft not found.")
        store.delete(draft_id)
        return {"ok": True}

    def gone_page(draft_id: str, theme: str, now: int) -> str:
        removed_at = database.removed_at(draft_id, now) if is_draft_id(draft_id) else None
        if removed_at is None:
            return render_not_found(theme)
        return render_expired(theme, removed_at, config.display_zone)

    @app.post("/d/{draft_id}")
    def unlock_draft(draft_id: str, token: str = Form(default="")) -> Response:
        # A path param can never hold a slash, but only a well-formed id is worth echoing
        # into a Location header at all.
        return unlock(f"/d/{draft_id}" if is_draft_id(draft_id) else "/", token)

    @app.api_route("/d/{draft_id}", methods=["GET", "HEAD"], response_class=HTMLResponse)
    def view_draft(
        draft_id: str,
        theme: str | None = None,
        authorization: str | None = Header(default=None),
        draftbin_token: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        now = int(time.time())
        if not reader_is_known(authorization, draftbin_token):
            # Checked ahead of any lookup on purpose. Prompting only for ids that resolve
            # would let a scanner map the whole keyspace without ever holding the token,
            # and two words is only ~1.7M ids.
            return unlock_page(f"/d/{draft_id}", None, 401)

        draft = database.find_live(draft_id, now) if is_draft_id(draft_id) else None
        stored = store.read(draft.id) if draft else None
        if draft is None or stored is None:
            if draft:
                logger.error("draft row without stored body", extra={"draft_id": draft.id})
            return HTMLResponse(
                gone_page(draft_id, resolve_theme(theme, None), now),
                status_code=404,
                headers=PRIVATE_HEADERS,
            )

        if draft.source_format == "html":
            return HTMLResponse(stored, headers=draft_headers)
        return HTMLResponse(
            render_markdown_document(
                stored,
                draft.title,
                draft.expires_at,
                resolve_theme(theme, draft.theme),
                config.display_zone,
            ),
            headers=draft_headers,
        )

    return app
