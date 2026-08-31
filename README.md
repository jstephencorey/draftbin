# draftbin

[![tests](https://github.com/jstephencorey/draftbin/actions/workflows/tests.yml/badge.svg)](https://github.com/jstephencorey/draftbin/actions/workflows/tests.yml)

Self-hosted private publishing for agent-generated documents. Post HTML or markdown, get
back a URL you can open on any device that holds your token, and have it delete itself in
a month.

Built for the workflow where a coding agent produces a plan, an analysis, or a day's
writing, and you want to _read_ it in a browser instead of scrolling a terminal.

```sh
curl -X POST https://drafts.example.com/api/upload/markdown \
  -H "Authorization: Bearer $DRAFTBIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"markdown": "# The plan\n\nStep one.", "filename": "plan.md"}'

{"id":"broad-half","url":"https://drafts.example.com/d/broad-half", ...}
```

Markdown is rendered to a styled standalone document — tables, footnotes, task lists,
definition lists, syntax-highlighted code, light/dark palettes, a collapsible contents
list, and a print stylesheet. HTML uploads are stored and served byte for byte.

There is also a paste box on the homepage, for the times you want to publish something
without a terminal in front of you.

## Readable URLs

A draft id is two words from the [EFF short wordlist][eff] — `broad-half`, `velvet-sage`.
The wordlist earns its place: nothing over five characters, no word a prefix of another,
and near-homophones already removed, so an id survives being read down a phone or typed
on one. That is the whole point; the common move here is to publish on a laptop, text
yourself the link, and open it on a phone.

[eff]: https://www.eff.org/dice

The trade is keyspace. Two words is about 1.7 million combinations, against 128 bits for
the ids minted before the change, and that is small enough to enumerate. That no longer
matters much, because the id is not the credential: reading a draft takes the token. See
"Reading takes the token" below.

Ids are checked against live drafts **and** tombstones before being handed out, so an id
retires permanently. Reissuing one would silently point a link somebody still holds at
unrelated content. Ids minted before the switch still resolve, so links already written
into notes keep working.

## Reading takes the token

`GET /d/{id}` answers `401` and a token form unless the request carries the token, either
as the `draftbin_token` cookie or as a bearer header. Enter it once and the cookie keeps
that device unlocked for 30 days. It is the same `DRAFTBIN_TOKEN` that publishes, so
anyone you hand it to can publish and delete too — this is a single-user server.

Three details that are easy to get wrong:

- **The gate runs before the lookup.** Every well-formed id gets the same reply whether
  or not a draft is behind it. Prompting only for ids that resolve would let a scanner map
  a 1.7-million-id keyspace without ever holding the token.
- **The token form cannot be served under the draft CSP.** Draft responses set `sandbox`
  and `form-action 'none'`, which would leave the gate page unable to submit the very form
  that unlocks it. The gate carries the ordinary private headers instead.
- **The cookie is `SameSite=Lax`, not `Strict`.** Strict withholds the cookie when a draft
  link is clicked from another site, so an unlocked device would be asked for the token
  every time it arrived from Slack or webmail. Lax rides along on top-level navigation and
  is still withheld on cross-site `POST`, which is the request a hostile page would have to
  forge to publish on your behalf.

Nothing is retroactive: this protects drafts from here on, not links already shared.

## Why links still expire

Expiry used to be the only thing keeping a draft private, which is why the default was
measured in hours. Now that reading takes the token, expiry is housekeeping rather than
access control — it stops content accumulating on a public-facing host and limits what a
later compromise would expose. That is why the default is 30 days and the ceiling a year.

It cannot un-read a page someone already fetched, and it does not protect content behind
a token you have handed out. Publish accordingly.

Expiry is enforced two ways, and both matter:

- **At read time**, by comparing the stored timestamp on every request. A stalled
  background job can never cause expired content to keep being served.
- **By a sweeper**, which deletes rows and files. This reclaims disk and limits what a
  later compromise of the host would expose.

Both deletion paths drop the database row before the file, so a crash in between would
strand a file that nothing revisits — sweeping is driven off rows, and that row is gone.
Startup reconciles the two by deleting any stored file with no matching row.

Publishing again mints a **new** ID. A link that leaked before it expired stays dead.

## Revising a draft

`PUT /api/drafts/{id}/markdown` (or `/html`) swaps the body of a live draft and keeps
its ID, so a link already written into a note survives the revision. It takes the same
fields as the matching upload endpoint, and a draft may change format on the way — a
markdown draft replaced with HTML stops being themeable.

Replacing **resets the expiry**, exactly as publishing again would; otherwise a revision
made shortly before the deadline would produce a link that died minutes later. The
server maximum still caps each window.

An expired ID cannot be replaced — that would revive a link that may already have
leaked. Publish a new draft instead.

`PATCH /api/drafts/{id}` takes `ttl_seconds` alone and moves the expiry without touching
the body, for the case where you are still reading something that is about to lapse.
The new window runs from now and is capped the same way. An expired draft cannot be
extended either.

Both are ways to avoid rewriting the note that points at a draft; neither weakens expiry,
because every window is still bounded by `DRAFTBIN_MAX_TTL_SECONDS`.

## When a link is dead

Following a dead link gives a page that distinguishes the two cases: an ID that once
worked reads "no longer available … removed on _date_", and an ID that never existed
reads "does not exist". Without that split, a stale link in a note is indistinguishable
from a typo, and the reflex is to go looking for a bug that isn't there.

That is what the `tombstones` table is for. It holds an ID and a timestamp, never
content, and rows are purged after `DRAFTBIN_TOMBSTONE_RETENTION_SECONDS`. The trade is
small but real: for that window, the server confirms to anyone holding a URL that the ID
was once a draft. Set the retention to something short if that is not a trade you want.

## API

Everything but the landing page, the static assets, and `/healthz` needs the token. The
API endpoints take it as `Authorization: Bearer $DRAFTBIN_TOKEN`; the reader-facing pages
take either that or the `draftbin_token` cookie.

| Method   | Path                   | Purpose                                   |
| -------- | ---------------------- | ----------------------------------------- |
| `POST`   | `/api/upload`          | Publish a prebuilt HTML document          |
| `POST`   | `/api/upload/markdown` | Render markdown, then publish it          |
| `PUT`    | `/api/drafts/{id}/html`     | Replace a draft, keeping its URL     |
| `PUT`    | `/api/drafts/{id}/markdown` | Replace a draft, keeping its URL     |
| `PATCH`  | `/api/drafts/{id}`     | Push a live draft's expiry out             |
| `GET`    | `/api/drafts`          | List live drafts with their expiry times  |
| `DELETE` | `/api/drafts/{id}`     | Delete a draft before it expires          |
| `GET`    | `/d/{id}?theme=`       | View a draft, or the token form           |
| `HEAD`   | `/d/{id}`              | Check a link without fetching the body    |
| `POST`   | `/d/{id}`              | Unlock this device, then land on the draft |
| `GET`    | `/drafts`              | Everything you have published, as a page  |
| `POST`   | `/drafts`              | Unlock this device, then land on the list |
| `GET`    | `/`                    | Landing page and paste box                |
| `POST`   | `/paste`               | Publish from the paste box (form-encoded) |
| `GET`    | `/static/fonts/{file}` | The reading face (public, cacheable)      |
| `GET`    | `/favicon.ico`         | Tab icon, for browsers that go looking     |
| `GET`    | `/static/icons/icon.svg` | Tab icon, at any size                   |
| `GET`    | `/healthz`             | Liveness probe                            |

`GET /drafts` is the reader-facing twin of `GET /api/drafts`: the same live drafts, newest
first, as titles you can click rather than JSON. It is the answer to "what do I still have
out there", which matters more now that drafts live for a month by default.

`DRAFTBIN_MAX_UPLOAD_BYTES` is enforced twice: against `Content-Length` before the
request is read, and against the rendered document before it is stored. The early check
matters because FastAPI buffers the request body *before* it evaluates the token
dependency, so bearer auth alone cannot stop an anonymous caller sending a huge payload.
A chunked request carries no `Content-Length` and is only caught by the second check.

`POST /api/upload` takes `html`, plus optional `filename` and `ttl_seconds`.
`POST /api/upload/markdown` takes `markdown`, plus optional `filename`, `title`,
`theme`, and `ttl_seconds`. A `ttl_seconds` above the server maximum is rejected rather
than silently clamped.

Responses carry a `content_hash` over the **stored body** — `sha256:` plus the digest.
For an HTML upload the stored body is the file you sent, so the hash identifies that
file. For markdown it is the rendered fragment, not your `.md`, so it tells you whether
two drafts hold the same document but cannot be recomputed from the source. Its use is
comparing drafts to each other and confirming a replacement actually changed something.

Markdown titles resolve in order: explicit `title`, then the first `# ` heading, then
the filename stem, then `Untitled draft`. HTML uploads have no `title` field — the
document names itself, so the `<title>` element is read out of it, falling back to the
filename stem and then `Untitled draft`.

## The paste box

`GET /` shows a textarea, an optional title, and a token field; `POST /paste` renders the
text as markdown, publishes it, and redirects you to the new draft, so the URL lands in
the address bar ready to share.

A form cannot send an `Authorization` header without JavaScript, and the CSP rules that
out, so the token arrives in a field once and then rides in a cookie — the same cookie
that unlocks reading:

```
Set-Cookie: draftbin_token=…; Max-Age=2592000; Path=/; HttpOnly; SameSite=Lax; Secure
```

`SameSite=Lax` withholds the cookie on cross-site `POST`, so no web page can post a form
at `/paste` and have the browser publish to your bin. It deliberately stops short of
`Strict`, which would also withhold it when you click your own draft link from another
site — see "Reading takes the token". `HttpOnly` is belt-and-braces given there is no
JavaScript anywhere here. `Secure` is set only when `DRAFTBIN_PUBLIC_BASE_URL` is
`https://`, because a Secure cookie is dropped over plain http and that would break local
development.

Two things to be aware of. The cookie **is** the token, so it exists in a browser's cookie
jar as well as wherever you keep it, and anyone holding your unlocked phone can read and
publish. And rotating the server token leaves a stale cookie behind — the next paste
answers `401`, clears the cookie, and shows the token field again rather than looping.

The redirect is relative, so whichever hostname you arrived on is the one you keep.

## Typography

Drafts are set in [Merriweather][mw], served from this origin rather than from a font
CDN. A `<link>` to Google Fonts would be blocked by `default-src 'none'` outright, and if
it weren't it would report every draft you open to a third party. Shipping the files is
also the only way the face renders on a phone, where neither Merriweather nor Garamond is
installed.

[mw]: https://github.com/SorkinType/Merriweather

Both faces are variable across the weight axis, so one file per style covers regular and
bold. `latin` and `latin-ext` are split on `unicode-range`, so a document with no
accented characters never fetches the ext files.

This is the one part of a draft worth caching, and it is served
`public, max-age=31536000, immutable` while everything else stays `no-store`. Only the
filenames in `fonts.py` resolve, so the route cannot be walked out of its folder.

`font-src` names the origin explicitly as well as `'self'`, because the `sandbox`
directive puts the document on an opaque origin and browsers have not always agreed on
what `'self'` means after that.

**A draft saved to disk loses the font** and falls back to Georgia, which is on every
platform worth caring about. That is the trade for not inlining ~270KB of base64 into
every document, and the fallback stack is chosen so the saved copy still reads properly.
The same applies to self-contained HTML uploads, which own their own styling anyway.

### The tab icon

An open book on the same brown, shipped twice. `icon.svg` is named in the `<head>` of
every page built by `render_page` and stays sharp at any size; `favicon.ico` is a
rasterised copy of it at 16, 32, 48 and 64 pixels. The ICO earns its place because an
HTML upload is served back byte for byte — nothing can be added to its `<head>`, so the
browser's own probe of `/favicon.ico` is the only icon those drafts will ever get. If the
artwork changes, redraw the ICO from the SVG.

Favicons are fetched under `img-src`, which is why that directive names the origin the
same way `font-src` does.

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

The contents list rides on the same property. It is read back out of the stored body at
request time rather than recorded at upload, from the `h2` and `h3` anchors, and appears
only once a document has three or more of them. `h1` is the title and `h4` is too fine
to navigate by, so neither is listed. It is a `<details>` element, since the CSP rules
out any JavaScript, and it is hidden when printing.

**HTML uploads are not themeable.** They are stored and served byte for byte, so
`?theme=` is ignored on them; the document you uploaded owns its own styling. The
`themeable` field in API responses tells you which kind you have.

## Serving it

Drafts are served with:

```
Content-Security-Policy: sandbox allow-popups allow-popups-to-escape-sandbox;
  default-src 'none'; style-src 'unsafe-inline'; font-src 'self' <base-url>;
  img-src 'self' <base-url> https: data:; base-uri 'none'; form-action 'none';
  frame-ancestors 'none'
Cache-Control: no-store, private, must-revalidate
Referrer-Policy: no-referrer
X-Robots-Tag: noindex, nofollow, noarchive, nosnippet
```

`default-src 'none'` is what actually prevents script execution; the `sandbox`
directive adds opaque-origin isolation on top. That combination means no JavaScript,
no external stylesheets, and no third-party web fonts in published documents — inline
`<style>` only, and the one self-hosted face named by `font-src`. Mermaid diagrams and JS
charts will not run.

Markdown drafts get a second, independent barrier: raw HTML embedded in the markdown is
filtered to an allowlist before it is stored, so a `<script>` or `<iframe>` becomes
visible escaped text rather than a tag. That matters because the CSP is a *header* — a
draft saved to disk and reopened from `file://` carries no CSP at all, and that saved
copy is often the durable record. `<details>`, `<summary>`, inline SVG, tables, and
ordinary formatting all pass through; event handlers and `javascript:` URLs do not.
HTML uploads are **not** filtered — they are served byte for byte by definition, and
the CSP is their only barrier.

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
| `DRAFTBIN_TOKEN`                  | _required_              | Token for reading and publishing; 20+ chars |
| `DRAFTBIN_PUBLIC_BASE_URL`        | `http://localhost:8000` | Origin returned URLs are built from         |
| `DRAFTBIN_THEME`                  | `auto`                  | Default theme; `?theme=` overrides per view |
| `DRAFTBIN_TIMEZONE`               | `UTC`                   | IANA zone for dates shown to readers        |
| `DRAFTBIN_DATA_DIR`               | `.local`                | `/data` in the container                    |
| `DRAFTBIN_DEFAULT_TTL_SECONDS`    | `2592000`               | 30 days                                     |
| `DRAFTBIN_MAX_TTL_SECONDS`        | `31536000`              | 365 days; caps per-upload overrides         |
| `DRAFTBIN_MAX_UPLOAD_BYTES`       | `2097152`               | 2 MiB; bounds the request and the document  |
| `DRAFTBIN_SWEEP_INTERVAL_SECONDS` | `300`                   | How often expired drafts are deleted        |
| `DRAFTBIN_TOMBSTONE_RETENTION_SECONDS` | `2592000`          | 30 days; how long a dead ID says "expired"  |

`DRAFTBIN_THEME` sets the default for markdown drafts that don't specify one and are
viewed without `?theme=`. See [Theming](#theming) for the full precedence chain.

`DRAFTBIN_TIMEZONE` applies only to dates rendered into pages a person reads — the
expiry line at the foot of a draft and the expired page. API responses keep reporting
UTC in ISO 8601, because a caller wants an unambiguous instant it can convert itself.

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

Draft ids are built from the [EFF short wordlist](https://www.eff.org/dice), CC BY 3.0
US. Merriweather is under the SIL Open Font License; the text ships in
`draftbin/static/fonts/OFL.txt`.

Inspired by Postplan, Theo's static HTML draft host, and by
[PatchPage](https://github.com/allisonmahmood/PatchPage), an open-source
self-hostable take on the same idea. draftbin is a separate implementation with
different priorities: python, single-user, markdown-first, expiring by default.

## License

MIT
