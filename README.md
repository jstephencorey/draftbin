# draftbin

Self-hosted ephemeral publishing for agent-generated documents. Post HTML or markdown,
get back an unlisted URL you can open anywhere, and have it delete itself after a day.

Built for the workflow where a coding agent produces a plan, an analysis, or a day's
writing, and you want to _read_ it in a browser instead of scrolling a terminal.

```sh
curl -X POST https://drafts.example.com/api/upload/markdown \
  -H "Authorization: Bearer $DRAFTBIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"markdown": "# The plan\n\nStep one.", "filename": "plan.md"}'

{"id":"UH4jXBAR958NTaH1e0Blhg","url":"https://drafts.example.com/d/UH4jXBAR958NTaH1e0Blhg", ...}
```

Markdown is rendered to a styled standalone document — tables, footnotes, task lists,
definition lists, syntax-highlighted code, light/dark palettes, and a print stylesheet.
HTML uploads are stored and served byte for byte.

## Why links expire

Draft URLs are public and unlisted: possession of the link is the only authorization.
That is a deliberate trade for convenience, and expiry is what makes it tolerable. It
bounds how long a leaked link stays useful and keeps internal content from
accumulating on a public-facing host.

It does **not** protect content that leaks and gets read inside the window, and it
cannot un-read a page someone already fetched. Publish accordingly.

Expiry is enforced two ways, and both matter:

- **At read time**, by comparing the stored timestamp on every request. A stalled
  background job can never cause expired content to keep being served.
- **By a sweeper**, which deletes rows and files. This reclaims disk and limits what a
  later compromise of the host would expose.

Both deletion paths drop the database row before the file, so a crash in between would
strand a file that nothing revisits — sweeping is driven off rows, and that row is gone.
Startup reconciles the two by deleting any stored file with no matching row.

Republishing mints a **new** ID. A link that leaked before it expired stays dead.

## API

Uploads and management need `Authorization: Bearer $DRAFTBIN_TOKEN`. Viewing does not.

| Method   | Path                   | Purpose                                   |
| -------- | ---------------------- | ----------------------------------------- |
| `POST`   | `/api/upload`          | Publish a prebuilt HTML document          |
| `POST`   | `/api/upload/markdown` | Render markdown, then publish it          |
| `GET`    | `/api/drafts`          | List live drafts with their expiry times  |
| `DELETE` | `/api/drafts/{id}`     | Delete a draft before it expires          |
| `GET`    | `/d/{id}?theme=`       | View a draft (public, unlisted, expiring) |
| `HEAD`   | `/d/{id}`              | Check a link without fetching the body    |
| `GET`    | `/healthz`             | Liveness probe                            |

`DRAFTBIN_MAX_UPLOAD_BYTES` is enforced twice: against `Content-Length` before the
request is read, and against the rendered document before it is stored. The early check
matters because FastAPI buffers the request body *before* it evaluates the token
dependency, so bearer auth alone cannot stop an anonymous caller sending a huge payload.
A chunked request carries no `Content-Length` and is only caught by the second check.

`POST /api/upload` takes `html`, plus optional `filename` and `ttl_seconds`.
`POST /api/upload/markdown` takes `markdown`, plus optional `filename`, `title`,
`theme`, and `ttl_seconds`. A `ttl_seconds` above the server maximum is rejected rather
than silently clamped.

Markdown titles resolve in order: explicit `title`, then the first `# ` heading, then
the filename stem, then `Untitled draft`. HTML uploads have no `title` field — the
document names itself, so the `<title>` element is read out of it, falling back to the
filename stem and then `Untitled draft`.

## Theming

Markdown drafts store only a rendered body fragment; the document shell is assembled
per request. So the theme is a **read-time** decision, and any of three levels can set
it, in order of precedence:

1. `?theme=dark` on the view URL — per view, per reader, no republishing
2. `"theme": "dark"` in the upload body — pinned to that one draft
3. `DRAFTBIN_THEME` — the server default

Each is `auto`, `light`, or `dark`. An unrecognised `?theme=` value falls back to the
next level rather than erroring, since these URLs get hand-edited. `auto` follows the
reader's OS via `prefers-color-scheme`; `light` and `dark` are unconditional.

Because the shell is assembled at request time, editing the stylesheet also changes
**already-published** drafts — no republishing needed.

**HTML uploads are not themeable.** They are stored and served byte for byte, so
`?theme=` is ignored on them; the document you uploaded owns its own styling. The
`themeable` field in API responses tells you which kind you have.

## Serving it

Drafts are served with:

```
Content-Security-Policy: sandbox allow-popups allow-popups-to-escape-sandbox;
  default-src 'none'; style-src 'unsafe-inline'; img-src https: data:;
  base-uri 'none'; form-action 'none'; frame-ancestors 'none'
Cache-Control: no-store, private, must-revalidate
Referrer-Policy: no-referrer
X-Robots-Tag: noindex, nofollow, noarchive, nosnippet
```

`default-src 'none'` is what actually prevents script execution; the `sandbox`
directive adds opaque-origin isolation on top. That combination means no JavaScript,
no external stylesheets, and no web fonts in published documents — inline `<style>`
only. Mermaid diagrams and JS charts will not run.

`Referrer-Policy: no-referrer` is the non-obvious one. Without it, a reader clicking a
link inside a draft leaks the draft's secret URL to that third party in the `Referer`
header, which defeats the whole point of an unlisted URL.

Every response carries those four headers, not just draft views — `GET /api/drafts`
returns every live draft URL at once, so it is the last thing that should sit in a cache.
Only the CSP is draft-specific.

### Behind a Cloudflare tunnel

`docker-compose.yml` runs the app But assumes that you are running a CloudFlare tunnel separately. Make sure to not have Cloudflare caching the drafts.

## Configuration

| Variable                          | Default                 | Notes                                       |
| --------------------------------- | ----------------------- | ------------------------------------------- |
| `DRAFTBIN_TOKEN`                  | _required_              | Bearer token for uploads; 20+ chars         |
| `DRAFTBIN_PUBLIC_BASE_URL`        | `http://localhost:8000` | Origin returned URLs are built from         |
| `DRAFTBIN_THEME`                  | `auto`                  | Default theme; `?theme=` overrides per view |
| `DRAFTBIN_DATA_DIR`               | `.local`                | `/data` in the container                    |
| `DRAFTBIN_DEFAULT_TTL_SECONDS`    | `86400`                 | 24 hours                                    |
| `DRAFTBIN_MAX_TTL_SECONDS`        | `604800`                | 7 days; caps per-upload overrides           |
| `DRAFTBIN_MAX_UPLOAD_BYTES`       | `2097152`               | 2 MiB; bounds the request and the document  |
| `DRAFTBIN_SWEEP_INTERVAL_SECONDS` | `300`                   | How often expired drafts are deleted        |

`DRAFTBIN_THEME` sets the default for markdown drafts that don't specify one and are
viewed without `?theme=`. See [Theming](#theming) for the full precedence chain.

Generate a token with:

```sh
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Running it

```sh
cp .env.example .env    # then fill in DRAFTBIN_TOKEN
docker compose up -d --build
```

Locally, without Docker:

```sh
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
DRAFTBIN_TOKEN=local-dev-token-1234567890 .venv/bin/python -m draftbin
.venv/bin/python -m pytest
```

Metadata lives in SQLite and rendered documents live as files, both under
`DRAFTBIN_DATA_DIR`. Requires SQLite 3.35+ (checked at startup) and Python 3.11+.

## Credit

Inspired by Postplan, Theo's static HTML draft host, and by
[PatchPage](https://github.com/allisonmahmood/PatchPage), an open-source
self-hostable take on the same idea. draftbin is a separate implementation with
different priorities: python, single-user, markdown-first, expiring by default.

## License

MIT
