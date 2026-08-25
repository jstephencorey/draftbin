from html.parser import HTMLParser


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
