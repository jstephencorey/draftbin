"""The tab icon: an open book, in the same brown the drafts are set in.

Two files, because the two ways a browser finds an icon do not overlap. Markdown drafts
and the landing page are built by `render_page`, which can name the SVG and get an icon
that stays sharp at any size. An HTML upload is served back byte for byte, so nothing can
be added to its `<head>` — those rely on the browser probing `/favicon.ico` at the root,
and that probe wants a real ICO.

favicon.ico is a rasterised copy of icon.svg at 16, 32, 48 and 64 pixels; redraw it if the
artwork ever changes.
"""

from pathlib import Path

ICONS_DIR = Path(__file__).resolve().parent / "static" / "icons"

SVG_ICON = ICONS_DIR / "icon.svg"
ICO_ICON = ICONS_DIR / "favicon.ico"

SVG_ICON_URL = "/static/icons/icon.svg"
ICO_ICON_URL = "/favicon.ico"

# Shorter than the fonts', which are named once and never edited again. This one can be
# replaced in place, and a week is already long enough to never be fetched twice.
ICON_CACHE_CONTROL = "public, max-age=604800"

# A browser that understands the SVG takes it and ignores the line above; one that does
# not falls back to the ICO. The explicit `sizes` is what lets the first kind decide
# without fetching the ICO to find out how big it is.
ICON_LINK_TAGS = (
    f'<link rel="icon" href="{ICO_ICON_URL}" sizes="32x32">\n'
    f'<link rel="icon" href="{SVG_ICON_URL}" type="image/svg+xml">'
)
