"""Allowlist filter for the raw HTML CommonMark lets through verbatim.

The CSP is what actually stops a script running on the live URL, but it is a *header*:
a draft saved to disk and reopened from file:// years later carries no CSP at all, and
that saved copy is the durable record. So the markup itself is filtered too.

Disallowed tags are escaped rather than dropped, so an author sees their tag rendered as
text and knows it was rejected, instead of watching content silently disappear.
"""

from html import escape
from html.parser import HTMLParser

TEXT_TAGS = frozenset(
    """
    p br hr span div section article header footer aside
    h1 h2 h3 h4 h5 h6
    blockquote pre code kbd samp var em strong b i u s small
    sub sup mark abbr cite q time del ins dfn
    ul ol li dl dt dd
    table thead tbody tfoot tr th td caption colgroup col
    a img figure figcaption details summary input
    """.split()
)

SVG_TAGS = frozenset(
    """
    svg g path circle ellipse rect line polyline polygon text tspan
    defs marker use title desc lineargradient radialgradient stop
    clippath mask pattern symbol
    """.split()
)

ALLOWED_TAGS = TEXT_TAGS | SVG_TAGS

GLOBAL_ATTRS = frozenset({"class", "id", "title", "lang", "dir", "style", "role", "aria-label"})

TAG_ATTRS = {
    "a": {"href", "rel", "target"},
    "img": {"src", "alt", "width", "height", "loading"},
    "td": {"colspan", "rowspan", "headers", "align"},
    "th": {"colspan", "rowspan", "scope", "abbr", "align"},
    "col": {"span"},
    "colgroup": {"span"},
    "ol": {"start", "type", "reversed"},
    "li": {"value"},
    "details": {"open"},
    # The task list plugin renders its checkbox as raw HTML, so this filter sees it too.
    # An input is inert here anyway: no script may run and form-action is 'none'.
    "input": {"type", "checked", "disabled"},
    "time": {"datetime"},
    "q": {"cite"},
    "blockquote": {"cite"},
}

# Presentation attributes, shared across every SVG element rather than tracked per tag.
SVG_ATTRS = frozenset(
    """
    xmlns viewbox preserveaspectratio width height x y x1 y1 x2 y2 cx cy r rx ry
    d points transform fill stroke stroke-width stroke-linecap stroke-linejoin
    stroke-dasharray stroke-dashoffset opacity fill-opacity fill-rule stroke-opacity
    text-anchor dominant-baseline font-family font-size font-weight letter-spacing
    offset stop-color stop-opacity gradientunits gradienttransform spreadmethod
    markerwidth markerheight refx refy orient markerunits patternunits
    clip-path clip-rule mask href
    """.split()
)

VOID_TAGS = frozenset({"br", "hr", "img", "col", "input"})

SAFE_URL_SCHEMES = ("http://", "https://", "mailto:")


def allowed_attribute(tag: str, name: str) -> bool:
    if tag in SVG_TAGS:
        return name in SVG_ATTRS or name in GLOBAL_ATTRS
    return name in GLOBAL_ATTRS or name in TAG_ATTRS.get(tag, frozenset())


def safe_url(tag: str, value: str) -> bool:
    """Fragments and ordinary web links only; data: images because img-src permits them."""
    url = value.strip().lower()
    if url.startswith("#") or url.startswith(SAFE_URL_SCHEMES):
        return True
    return tag == "img" and url.startswith("data:image/")


def render_attribute(tag: str, name: str, value: str | None) -> str:
    if not allowed_attribute(tag, name):
        return ""
    if name in ("href", "src") and not safe_url(tag, value or ""):
        return ""
    if value is None:
        return f" {name}"
    return f' {name}="{escape(value, quote=True)}"'


class Sanitizer(HTMLParser):
    """Filters tags and attributes without trying to balance the tree.

    markdown-it hands raw HTML over in fragments — an opening `<details>` and its closing
    tag arrive as separate tokens with markdown in between — so any attempt to close what
    a fragment leaves open would corrupt the document.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def emit_tag(self, tag: str, attrs: list, self_closing: bool) -> None:
        if tag not in ALLOWED_TAGS:
            self.parts.append(escape(self.get_starttag_text() or ""))
            return
        rendered = "".join(render_attribute(tag, name, value) for name, value in attrs)
        closer = " />" if self_closing or tag in VOID_TAGS else ">"
        self.parts.append(f"<{tag}{rendered}{closer}")

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self.emit_tag(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self.emit_tag(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        if tag not in ALLOWED_TAGS:
            self.parts.append(escape(f"</{tag}>"))
        elif tag not in VOID_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.parts.append(escape(data, quote=False))

    def handle_comment(self, data: str) -> None:
        pass

    def handle_decl(self, decl: str) -> None:
        pass

    def handle_pi(self, data: str) -> None:
        pass

    def unknown_decl(self, data: str) -> None:
        pass


def sanitize_html(fragment: str) -> str:
    """Attribute and tag names come back lowercased.

    That is fine for inline SVG: an HTML parser restores `viewbox` to `viewBox` and
    `lineargradient` to `linearGradient` from a fixed table, and the documents are always
    parsed as HTML, whether served or opened from disk.
    """
    sanitizer = Sanitizer()
    sanitizer.feed(fragment)
    sanitizer.close()
    return "".join(sanitizer.parts)
