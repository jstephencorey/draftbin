from dataclasses import dataclass
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from pygments.formatters import HtmlFormatter

from draftbin.fonts import FONT_FACE_CSS
from draftbin.html_document import Heading, outline
from draftbin.icons import ICON_LINK_TAGS

# Below this a contents list is longer than the navigation it saves.
MINIMUM_OUTLINE_ENTRIES = 3

LIGHT_VARS = """
  --bg: #fbf9f4;
  --fg: #23201b;
  --muted: #6c655a;
  --rule: #ded7c9;
  --accent: #8f4b1e;
  --code-bg: #f1ece1;
  --quote-bg: #f4efe4;
"""

DARK_VARS = """
  --bg: #191714;
  --fg: #e8e3d8;
  --muted: #a29a8c;
  --rule: #38332c;
  --accent: #e0a06a;
  --code-bg: #232019;
  --quote-bg: #201d18;
"""

BASE_CSS = """
*, *::before, *::after { box-sizing: border-box; }

html { -webkit-text-size-adjust: 100%; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: Merriweather, Georgia, "Iowan Old Style", "Times New Roman", serif;
  font-size: 1.125rem;
  line-height: 1.75;
  text-rendering: optimizeLegibility;
}

main {
  max-width: 42rem;
  margin: 0 auto;
  padding: 4rem 1.35rem 6rem;
}

h1, h2, h3, h4, h5, h6 {
  line-height: 1.3;
  margin: 2em 0 0.6em;
  font-weight: 700;
  letter-spacing: -0.01em;
}

h1 {
  font-size: 2.1rem;
  margin-top: 0;
  line-height: 1.2;
}

h2 {
  font-size: 1.5rem;
  padding-bottom: 0.3em;
  border-bottom: 1px solid var(--rule);
}

h3 { font-size: 1.22rem; }
h4 { font-size: 1.06rem; }
h5, h6 { font-size: 1rem; color: var(--muted); }

p, ul, ol, dl, blockquote, pre, details { margin: 0 0 1.3em; }

dt { font-weight: 700; margin-top: 1em; }
dd { margin: 0.2em 0 0.7em 1.5em; color: var(--muted); }

a {
  color: var(--accent);
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 0.17em;
}

.header-anchor {
  color: var(--muted);
  text-decoration: none;
  opacity: 0;
  margin-left: 0.35em;
  font-weight: 400;
}

h1:hover .header-anchor,
h2:hover .header-anchor,
h3:hover .header-anchor,
h4:hover .header-anchor { opacity: 1; }

ul, ol { padding-left: 1.5em; }
li { margin: 0.35em 0; }
li > ul, li > ol { margin: 0.35em 0; }

ul.contains-task-list { padding-left: 1.1em; }
li.task-list-item { list-style: none; }
li.task-list-item input { margin-right: 0.5em; }

blockquote {
  padding: 0.7em 1.2em;
  border-left: 3px solid var(--rule);
  background: var(--quote-bg);
  color: var(--muted);
  border-radius: 0 4px 4px 0;
}

blockquote > :last-child { margin-bottom: 0; }

/* Merriweather has a tall x-height, so a monospace at the usual 0.875em reads oversized
   next to it. */
code, kbd, pre, samp {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.82em;
}

code {
  background: var(--code-bg);
  padding: 0.15em 0.4em;
  border-radius: 4px;
}

pre {
  background: var(--code-bg);
  padding: 1em 1.2em;
  border-radius: 6px;
  overflow-x: auto;
  line-height: 1.55;
}

pre code {
  background: none;
  padding: 0;
  border-radius: 0;
}

/* Outrank the background Pygments ships on .highlight so all code blocks match. */
pre.highlight { background: var(--code-bg); }

.table-scroll {
  overflow-x: auto;
  margin: 0 0 1.3em;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9em;
  line-height: 1.5;
}

th, td {
  border: 1px solid var(--rule);
  padding: 0.5em 0.75em;
  text-align: left;
}

th { background: var(--quote-bg); font-weight: 700; }

img { max-width: 100%; height: auto; border-radius: 4px; }

hr {
  height: 1px;
  border: 0;
  background: var(--rule);
  margin: 2.75em 0;
}

.footnotes-sep { display: none; }

.footnotes {
  margin-top: 3em;
  padding-top: 1em;
  border-top: 1px solid var(--rule);
  font-size: 0.9em;
  color: var(--muted);
}

.draft-contents {
  margin: 0 0 2.75em;
  padding: 0.7em 1.2em;
  border: 1px solid var(--rule);
  border-radius: 6px;
  font-size: 0.9em;
}

.draft-contents summary {
  cursor: pointer;
  font-weight: 700;
  color: var(--muted);
}

.draft-contents ul {
  list-style: none;
  margin: 0.8em 0 0.3em;
  padding-left: 0;
}

.draft-contents li { margin: 0.3em 0; }
.draft-contents li.depth-3 { padding-left: 1.3em; }
.draft-contents a { text-decoration: none; }
.draft-contents a:hover { text-decoration: underline; }

.draft-meta {
  margin-top: 4em;
  padding-top: 1em;
  border-top: 1px solid var(--rule);
  font-size: 0.8em;
  color: var(--muted);
}

.paste-form { margin: 0 0 2em; }

.paste-form label {
  display: block;
  margin-bottom: 0.35em;
  font-size: 0.85em;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
}

.paste-form textarea,
.paste-form input {
  display: block;
  width: 100%;
  margin-bottom: 1.4em;
  padding: 0.7em 0.85em;
  background: var(--bg);
  color: var(--fg);
  border: 1px solid var(--rule);
  border-radius: 6px;
  font-family: inherit;
  font-size: 1rem;
  line-height: 1.6;
}

.paste-form textarea {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.85rem;
  resize: vertical;
}

.paste-form textarea:focus,
.paste-form input:focus {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.paste-form button {
  padding: 0.6em 1.6em;
  background: var(--accent);
  color: var(--bg);
  border: 0;
  border-radius: 6px;
  font-family: inherit;
  font-size: 1rem;
  font-weight: 700;
  cursor: pointer;
}

.paste-hint {
  display: inline-block;
  margin-left: 1em;
  font-size: 0.85em;
  color: var(--muted);
}

.paste-error {
  padding: 0.7em 1.1em;
  margin: 0 0 1.5em;
  border: 1px solid var(--accent);
  border-radius: 6px;
  color: var(--accent);
  font-size: 0.9em;
}

.draft-list {
  list-style: none;
  padding-left: 0;
}

.draft-list li {
  margin: 0;
  padding: 0.9em 0;
  border-bottom: 1px solid var(--rule);
}

.draft-list a {
  text-decoration: none;
  font-weight: 700;
}

.draft-list a:hover { text-decoration: underline; }

.draft-list-meta {
  display: block;
  margin-top: 0.2em;
  font-size: 0.8em;
  color: var(--muted);
}

@media print {
  body { background: #fff; color: #000; font-size: 11pt; }
  main { max-width: none; padding: 0; }
  pre, code, blockquote, th { background: none; }
  pre, blockquote { border: 1px solid #ccc; }
  .draft-meta, .heading-anchor, .draft-contents, .paste-form { display: none; }
}
"""

LIGHT_HIGHLIGHT = HtmlFormatter(style="default").get_style_defs(".highlight")
DARK_HIGHLIGHT = HtmlFormatter(style="monokai").get_style_defs(".highlight")

THEMES = ("auto", "light", "dark")


@dataclass(frozen=True)
class PasteForm:
    """What the homepage form should show, including anything a failed submit must keep."""

    text: str = ""
    title: str = ""
    needs_token: bool = True
    error: str | None = None


def theme_css(theme: str) -> str:
    """Emit the palette for a fixed theme, or one that follows the reader's OS setting."""
    if theme == "dark":
        return f":root {{ color-scheme: dark;{DARK_VARS}}}\n{DARK_HIGHLIGHT}"
    if theme == "light":
        return f":root {{ color-scheme: light;{LIGHT_VARS}}}\n{LIGHT_HIGHLIGHT}"
    return "\n".join(
        [
            f":root {{ color-scheme: light dark;{LIGHT_VARS}}}",
            LIGHT_HIGHLIGHT,
            "@media (prefers-color-scheme: dark) {",
            f":root {{{DARK_VARS}}}",
            DARK_HIGHLIGHT,
            "}",
        ]
    )


def format_timestamp(epoch_seconds: int, zone: ZoneInfo) -> str:
    """Reader-facing dates only. The API keeps reporting UTC, which is what machines want."""
    return datetime.fromtimestamp(epoch_seconds, tz=zone).strftime("%Y-%m-%d %H:%M %Z")


def format_duration(seconds: int) -> str:
    """Lifetimes are days now more often than hours, and "720 hours" reads as a mistake."""
    hours = seconds / 3600
    if hours < 48:
        return f"{hours:g} hours"
    return f"{hours / 24:g} days"


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    return f"{size_bytes / 1024:.0f} KB"


def render_page(title: str, body_html: str, theme: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>{escape(title)}</title>
{ICON_LINK_TAGS}
<style>
{FONT_FACE_CSS}
{theme_css(theme)}
{BASE_CSS}
</style>
</head>
<body>
<main>
{body_html}
</main>
</body>
</html>
"""


def render_contents(headings: list[Heading]) -> str:
    """A disclosure element, because navigation has to work with no JavaScript at all."""
    if len(headings) < MINIMUM_OUTLINE_ENTRIES:
        return ""
    items = "\n".join(
        f'<li class="depth-{heading.level}">'
        f'<a href="#{escape(heading.anchor, quote=True)}">{escape(heading.text)}</a></li>'
        for heading in headings
    )
    return (
        '<details class="draft-contents" open><summary>Contents</summary>\n'
        f"<ul>\n{items}\n</ul>\n</details>\n"
    )


def render_markdown_document(
    body_html: str, title: str, expires_at: int, theme: str, zone: ZoneInfo
) -> str:
    meta = (
        '<p class="draft-meta">Published with draftbin &middot; link expires '
        f"{format_timestamp(expires_at, zone)}</p>"
    )
    contents = render_contents(outline(body_html))
    return render_page(title, f"{contents}{body_html}\n{meta}", theme)


def render_token_field(needs_token: bool) -> str:
    """Once the cookie is set the field is gone, which is the whole point of the cookie."""
    if not needs_token:
        return ""
    return """<label for="token">Token</label>
<input id="token" name="token" type="password" autocomplete="current-password"
       placeholder="DRAFTBIN_TOKEN">
"""


def render_landing(
    public_base_url: str, default_ttl_seconds: int, theme: str, form: PasteForm
) -> str:
    lifetime = format_duration(default_ttl_seconds)
    error = f'<p class="paste-error">{escape(form.error)}</p>\n' if form.error else ""
    return render_page(
        "draftbin",
        f"""
<h1>draftbin</h1>
<p>Paste something below and get back a private link that reads well on a phone and
deletes itself in {lifetime}. Markdown is rendered; plain text is fine too.</p>
{error}<form class="paste-form" method="post" action="/paste">
<label for="text">Text</label>
<textarea id="text" name="text" rows="16" required
          placeholder="# Notes&#10;&#10;Paste markdown or plain text..."
>{escape(form.text)}</textarea>
<label for="title">Title <span>(optional)</span></label>
<input id="title" name="title" type="text" value="{escape(form.title, quote=True)}"
       placeholder="Taken from the first heading if left blank">
{render_token_field(form.needs_token)}<button type="submit">Publish</button>
<span class="paste-hint">Expires in {lifetime}.</span>
</form>
<p><a href="/drafts">Everything you have published</a></p>
<h2>From a script</h2>
<pre><code>curl -X POST {escape(public_base_url)}/api/upload/markdown \\
  -H "Authorization: Bearer $DRAFTBIN_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"markdown": "# Hello", "filename": "notes.md"}}'</code></pre>
<p>Post to <code>/api/upload</code> with an <code>html</code> field to publish a
prebuilt document instead. Override the lifetime per upload with
<code>ttl_seconds</code>.</p>
""",
        theme,
    )


def render_unlock(theme: str, action: str, error: str | None) -> str:
    """Says nothing about whether the id behind it resolves, because it is shown before
    anything is looked up. Enumerating the keyspace has to learn nothing from the reply."""
    message = f'<p class="paste-error">{escape(error)}</p>\n' if error else ""
    return render_page(
        "draftbin",
        f"""
<h1>Enter your token</h1>
<p>Drafts on this server are private. Enter the token once and this device stays
unlocked.</p>
{message}<form class="paste-form" method="post" action="{escape(action, quote=True)}">
{render_token_field(True)}<button type="submit">Unlock</button>
</form>
""",
        theme,
    )


@dataclass(frozen=True)
class IndexEntry:
    id: str
    title: str
    created_at: int
    expires_at: int
    size_bytes: int


def render_index(entries: list[IndexEntry], theme: str, zone: ZoneInfo) -> str:
    """Links are relative, so the listing keeps whatever hostname you arrived on — the
    same reason the paste form redirects relatively."""
    if not entries:
        body = "<p>Nothing published right now.</p>"
    else:
        items = "\n".join(
            f'<li><a href="/d/{escape(entry.id, quote=True)}">{escape(entry.title)}</a>'
            f'<span class="draft-list-meta">'
            f"published {format_timestamp(entry.created_at, zone)} &middot; "
            f"expires {format_timestamp(entry.expires_at, zone)} &middot; "
            f"{format_size(entry.size_bytes)}</span></li>"
            for entry in entries
        )
        body = f'<ul class="draft-list">\n{items}\n</ul>'
    return render_page(
        "Published drafts",
        f'<h1>Published drafts</h1>\n{body}\n<p><a href="/">Publish another</a></p>\n',
        theme,
    )


def render_not_found(theme: str) -> str:
    return render_page(
        "Not found",
        """
<h1>Not found</h1>
<p>This draft does not exist, or its link has expired. Expired drafts are deleted
and cannot be recovered &mdash; publish again to get a new link.</p>
""",
        theme,
    )


def render_expired(theme: str, removed_at: int, zone: ZoneInfo) -> str:
    """Says the link worked once, which "not found" cannot: a dead link then reads as
    expired rather than as a typo somewhere between here and the note it came from."""
    return render_page(
        "Expired",
        f"""
<h1>Expired</h1>
<p>This draft was published and is no longer available. It was removed on
{format_timestamp(removed_at, zone)}.</p>
<p>Expired drafts are deleted and cannot be recovered &mdash; publish again to get a
new link.</p>
""",
        theme,
    )
