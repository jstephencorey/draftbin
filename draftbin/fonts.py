"""Merriweather, served from this origin rather than from a font CDN.

A draft's CSP is `default-src 'none'` plus a `sandbox` directive, so a Google Fonts
`<link>` would be blocked outright and, if it weren't, would tell a third party every
time a draft was opened. Shipping the files makes the face render the same on a phone,
where neither Merriweather nor Garamond is installed.

Both faces are variable across the weight axis, so one file per style covers regular and
bold. `latin-ext` is worth its size here: work notes are full of accented names.

Merriweather is under the SIL Open Font License; see static/fonts/OFL.txt.
"""

from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parent / "static" / "fonts"

# Splitting on unicode-range means a document with no accented characters never fetches
# the latin-ext files at all.
LATIN = (
    "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, "
    "U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, "
    "U+FEFF, U+FFFD"
)
LATIN_EXT = (
    "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, "
    "U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, "
    "U+2113, U+2C60-2C7F, U+A720-A7FF"
)

FONT_FILES = {
    "merriweather-latin.woff2": ("normal", LATIN),
    "merriweather-latin-ext.woff2": ("normal", LATIN_EXT),
    "merriweather-italic-latin.woff2": ("italic", LATIN),
    "merriweather-italic-latin-ext.woff2": ("italic", LATIN_EXT),
}

FONT_URL_PREFIX = "/static/fonts"

# A year, because the filenames are stable and the bytes never change. Drafts themselves
# stay no-store; this is the one thing here worth caching.
FONT_CACHE_CONTROL = "public, max-age=31536000, immutable"


def font_face(filename: str, style: str, unicode_range: str) -> str:
    return f"""@font-face {{
  font-family: Merriweather;
  font-style: {style};
  font-weight: 400 700;
  font-display: swap;
  src: url({FONT_URL_PREFIX}/{filename}) format("woff2");
  unicode-range: {unicode_range};
}}"""


FONT_FACE_CSS = "\n".join(
    font_face(filename, style, unicode_range)
    for filename, (style, unicode_range) in FONT_FILES.items()
)


def font_path(filename: str) -> Path | None:
    """Only the names above resolve, so the URL can never reach outside the font folder."""
    if filename not in FONT_FILES:
        return None
    path = FONTS_DIR / filename
    return path if path.is_file() else None
