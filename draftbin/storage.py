from pathlib import Path


class HtmlStore:
    def __init__(self, root: Path):
        self.root = root

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, draft_id: str) -> Path:
        return self.root / f"{draft_id}.html"

    def write(self, draft_id: str, html: str) -> None:
        self.path_for(draft_id).write_text(html, encoding="utf-8")

    def read(self, draft_id: str) -> str | None:
        path = self.path_for(draft_id)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def delete(self, draft_id: str) -> None:
        self.path_for(draft_id).unlink(missing_ok=True)
