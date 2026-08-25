import os
from pathlib import Path

TEMPORARY_SUFFIX = ".tmp"


class HtmlStore:
    def __init__(self, root: Path):
        self.root = root

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, draft_id: str) -> Path:
        return self.root / f"{draft_id}.html"

    def write(self, draft_id: str, html: str) -> None:
        """Rename into place so a crash mid-write leaves the old body, not half the new one.

        Replacing a draft reuses its id, so the target often already exists and a reader
        can be part way through it.
        """
        destination = self.path_for(draft_id)
        staged = destination.with_name(destination.name + TEMPORARY_SUFFIX)
        staged.write_text(html, encoding="utf-8")
        os.replace(staged, destination)

    def discard_staged_writes(self) -> None:
        for path in self.root.glob(f"*{TEMPORARY_SUFFIX}"):
            path.unlink(missing_ok=True)

    def read(self, draft_id: str) -> str | None:
        path = self.path_for(draft_id)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def delete(self, draft_id: str) -> None:
        self.path_for(draft_id).unlink(missing_ok=True)
