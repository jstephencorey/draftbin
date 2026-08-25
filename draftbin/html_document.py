from dataclasses import dataclass
from html.parser import HTMLParser

# The anchors plugin gives h1-h4 an id, but h1 is the document title and h4 is too fine
# grained to navigate by, so the outline is built from the two levels in between.
OUTLINE_TAGS = {"h2": 2, "h3": 3}
PERMALINK_CLASS = "header-anchor"


class TitleReader(HTMLParser):
    """Collects the first <title>, ignoring any later one."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.collecting = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "title" and self.title is None:
            self.collecting = True

    def handle_data(self, data: str) -> None:
        if self.collecting:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self.collecting:
            self.collecting = False
            self.title = "".join(self.parts).strip() or None


def document_title(html: str) -> str | None:
    reader = TitleReader()
    reader.feed(html)
    reader.close()
    return reader.title


@dataclass(frozen=True)
class Heading:
    level: int
    anchor: str
    text: str


class OutlineReader(HTMLParser):
    """Collects headings and their anchors, ignoring the permalink glyph inside each one."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[Heading] = []
        self.level = 0
        self.anchor = ""
        self.parts: list[str] = []
        self.in_permalink = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attributes = dict(attrs)
        if self.level:
            self.in_permalink = tag == "a" and PERMALINK_CLASS in (attributes.get("class") or "")
        elif tag in OUTLINE_TAGS and attributes.get("id"):
            self.level = OUTLINE_TAGS[tag]
            self.anchor = attributes["id"]
            self.parts = []

    def handle_endtag(self, tag: str) -> None:
        if not self.level:
            return
        if tag == "a":
            self.in_permalink = False
        elif OUTLINE_TAGS.get(tag) == self.level:
            text = "".join(self.parts).strip()
            if text:
                self.headings.append(Heading(self.level, self.anchor, text))
            self.level = 0

    def handle_data(self, data: str) -> None:
        if self.level and not self.in_permalink:
            self.parts.append(data)


def outline(html: str) -> list[Heading]:
    """Read the outline back out of a stored body rather than recording it at upload time.

    Keeps the whole document shell a read-time decision, the same way themes are, so
    already-published drafts pick this up without being republished.
    """
    reader = OutlineReader()
    reader.feed(html)
    reader.close()
    return reader.headings
