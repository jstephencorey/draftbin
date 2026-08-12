# draftbin

Self-hosted ephemeral publishing for agent-generated documents. Post HTML or markdown,
get back an unlisted URL you can open anywhere, and have it delete itself after a day.

Built for the workflow where a coding agent produces a plan, an analysis, or a day's
writing, and you want to *read* it in a browser instead of scrolling a terminal.

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

Republishing mints a **new** ID. A link that leaked before it expired stays dead.

## API

Uploads and management need `Authorization: Bearer $DRAFTBIN_TOKEN`. Viewing does not.

| Method   | Path                    | Purpose                                        |
| -------- | ----------------------- | ---------------------------------------------- |
| `POST`   | `/api/upload`           | Publish a prebuilt HTML document               |
| `POST`   | `/api/upload/markdown`  | Render markdown, then publish it               |
| `GET`    | `/api/drafts`           | List live drafts with their expiry times       |
| `DELETE` | `/api/drafts/{id}`      | Delete a draft before it expires               |
| `GET`    | `/d/{id}`               | View a draft (public, unlisted, expiring)      |
| `GET`    | `/healthz`              | Liveness probe                                 |

`POST /api/upload` takes `html`, plus optional `filename` and `ttl_seconds`.
`POST /api/upload/markdown` takes `markdown`, plus optional `filename`, `title`, and
`ttl_seconds`. A `ttl_seconds` above the server maximum is rejected rather than
silently clamped.

Document titles resolve in order: explicit `title`, then the first `# ` heading, then
the filename stem, then `Untitled draft`.

## Serving it

Drafts are served with:

```
Content-Security-Policy: sandbox allow-popups allow-popups-to-escape-sandbox;
  default-src 'none'; style-src 'unsafe-inline'; img-src https: data:;
  base-uri 'none'; form-action 'none'
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

### Behind a Cloudflare tunnel

`docker-compose.yml` runs the app plus `cloudflared`, so nothing is exposed directly.
Set `CLOUDFLARE_TUNNEL_TOKEN` and point the tunnel's public hostname at
`http://draftbin:8000`.

Two things to get right on the Cloudflare side:

1. **Use a dedicated hostname** (`drafts.example.com`), not a path on a domain that
   hosts your other self-hosted apps. Keeps drafts out of any shared cookie scope.
2. **Confirm Cloudflare is not caching drafts.** Defaults don't cache HTML, but
   "Cache Everything" page rules and Automatic Platform Optimization do — and a cached
   response will outlive expiry. Add a Cache Rule bypassing cache for `/d/*` and check
   `curl -sI` shows `cf-cache-status: DYNAMIC` or `BYPASS`.

## Configuration

| Variable                          | Default                 | Notes                                          |
| --------------------------------- | ----------------------- | ---------------------------------------------- |
| `DRAFTBIN_TOKEN`                  | *required*              | Bearer token for uploads; 20+ chars            |
| `DRAFTBIN_PUBLIC_BASE_URL`        | `http://localhost:8000` | Origin returned URLs are built from            |
| `DRAFTBIN_THEME`                  | `auto`                  | `auto`, `light`, or `dark`                      |
| `DRAFTBIN_DATA_DIR`               | `.local`                | `/data` in the container                        |
| `DRAFTBIN_DEFAULT_TTL_SECONDS`    | `86400`                 | 24 hours                                        |
| `DRAFTBIN_MAX_TTL_SECONDS`        | `604800`                | 7 days; caps per-upload overrides               |
| `DRAFTBIN_MAX_UPLOAD_BYTES`       | `2097152`               | 2 MiB, measured on the rendered document        |
| `DRAFTBIN_SWEEP_INTERVAL_SECONDS` | `300`                   | How often expired drafts are deleted            |

`DRAFTBIN_THEME=auto` follows each reader's OS setting via `prefers-color-scheme`.
Setting `dark` or `light` is unconditional, which is what you want if you always read
in one mode regardless of what the machine is set to.

The theme is baked into each document when it's published, so a change applies to new
drafts only. With a 24-hour TTL, everything catches up within a day.

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
different priorities: single-user, markdown-first, expiring by default.

## License

MIT
