from datetime import datetime, timezone
from html import escape

from pygments.formatters import HtmlFormatter

LIGHT_VARS = """
  --bg: #fdfdfc;
  --fg: #1f2328;
  --muted: #656d76;
  --rule: #d8dee4;
  --accent: #0550ae;
  --code-bg: #f2f3f5;
  --quote-bg: #f6f8fa;
"""

DARK_VARS = """
  --bg: #16181d;
  --fg: #e3e6ea;
  --muted: #9198a1;
  --rule: #2f343d;
  --accent: #79b8ff;
  --code-bg: #22262d;
  --quote-bg: #1c1f25;
"""

BASE_CSS = """
*, *::before, *::after { box-sizing: border-box; }

html { -webkit-text-size-adjust: 100%; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 17px;
  line-height: 1.65;
}

main {
  max-width: 44rem;
  margin: 0 auto;
  padding: 3.5rem 1.25rem 5rem;
}

h1, h2, h3, h4, h5, h6 {
  line-height: 1.25;
  margin: 2.25em 0 0.75em;
  font-weight: 600;
}

h1 {
  font-size: 2rem;
  margin-top: 0;
  padding-bottom: 0.3em;
  border-bottom: 1px solid var(--rule);
}

h2 {
  font-size: 1.5rem;
  padding-bottom: 0.25em;
  border-bottom: 1px solid var(--rule);
}

h3 { font-size: 1.25rem; }
h4 { font-size: 1.05rem; }
h5, h6 { font-size: 1rem; color: var(--muted); }

p, ul, ol, dl, blockquote, pre, details { margin: 0 0 1.15em; }

dt { font-weight: 600; margin-top: 0.9em; }
dd { margin: 0.2em 0 0.6em 1.4em; color: var(--muted); }

a {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 0.15em;
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

ul, ol { padding-left: 1.6em; }
li { margin: 0.3em 0; }
li > ul, li > ol { margin: 0.3em 0; }

ul.contains-task-list { padding-left: 1.1em; }
li.task-list-item { list-style: none; }
li.task-list-item input { margin-right: 0.5em; }

blockquote {
  padding: 0.6em 1.1em;
  border-left: 3px solid var(--rule);
  background: var(--quote-bg);
  color: var(--muted);
  border-radius: 0 4px 4px 0;
}

blockquote > :last-child { margin-bottom: 0; }

code, kbd, pre, samp {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.875em;
}

code {
  background: var(--code-bg);
  padding: 0.15em 0.35em;
  border-radius: 4px;
}

pre {
  background: var(--code-bg);
  padding: 0.9em 1.1em;
  border-radius: 6px;
  overflow-x: auto;
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
  margin: 0 0 1.15em;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.94em;
}

th, td {
  border: 1px solid var(--rule);
  padding: 0.45em 0.7em;
  text-align: left;
}

th { background: var(--quote-bg); font-weight: 600; }

img { max-width: 100%; height: auto; border-radius: 4px; }

hr {
  height: 1px;
  border: 0;
  background: var(--rule);
  margin: 2.5em 0;
}

.footnotes-sep { display: none; }

.footnotes {
  margin-top: 3em;
  padding-top: 1em;
  border-top: 1px solid var(--rule);
  font-size: 0.9em;
  color: var(--muted);
}

.draft-meta {
  margin-top: 4em;
  padding-top: 1em;
  border-top: 1px solid var(--rule);
  font-size: 0.82em;
  color: var(--muted);
}

@media print {
  body { background: #fff; color: #000; font-size: 11pt; }
  main { max-width: none; padding: 0; }
  pre, code, blockquote, th { background: none; }
  pre, blockquote { border: 1px solid #ccc; }
  .draft-meta, .heading-anchor { display: none; }
}
"""

LIGHT_HIGHLIGHT = HtmlFormatter(style="default").get_style_defs(".highlight")
DARK_HIGHLIGHT = HtmlFormatter(style="monokai").get_style_defs(".highlight")

THEMES = ("auto", "light", "dark")


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


def format_timestamp(epoch_seconds: int) -> str:
    return (
        datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        .strftime("%Y-%m-%d %H:%M UTC")
    )


def render_page(title: str, body_html: str, theme: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>{escape(title)}</title>
<style>
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


def render_markdown_document(body_html: str, title: str, expires_at: int, theme: str) -> str:
    meta = (
        '<p class="draft-meta">Published with draftbin &middot; link expires '
        f"{format_timestamp(expires_at)}</p>"
    )
    return render_page(title, f"{body_html}\n{meta}", theme)


def render_landing(public_base_url: str, default_ttl_seconds: int, theme: str) -> str:
    hours = default_ttl_seconds / 3600
    return render_page(
        "draftbin",
        f"""
<h1>draftbin</h1>
<p>Ephemeral publishing for agent-generated HTML and markdown. Uploads need a bearer
token; draft URLs are unlisted, public, and expire automatically.</p>
<h2>Publish</h2>
<pre><code>curl -X POST {escape(public_base_url)}/api/upload/markdown \\
  -H "Authorization: Bearer $DRAFTBIN_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"markdown": "# Hello", "filename": "notes.md"}}'</code></pre>
<p>Post to <code>/api/upload</code> with an <code>html</code> field to publish a
prebuilt document instead. Default lifetime is {hours:g} hours; override per upload
with <code>ttl_seconds</code>.</p>
""",
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
