import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    filename      TEXT,
    source_format TEXT NOT NULL,
    theme         TEXT,
    created_at    INTEGER NOT NULL,
    expires_at    INTEGER NOT NULL,
    size_bytes    INTEGER NOT NULL,
    content_hash  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS drafts_expires_at ON drafts (expires_at);
"""


@dataclass(frozen=True)
class Draft:
    id: str
    title: str
    filename: str | None
    source_format: str
    theme: str | None
    created_at: int
    expires_at: int
    size_bytes: int
    content_hash: str


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        if sqlite3.sqlite_version_info < (3, 35):
            raise RuntimeError(
                f"SQLite 3.35+ required for DELETE ... RETURNING, found {sqlite3.sqlite_version}"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.executescript(SCHEMA)
            self.migrate_to_themed_bodies(connection)

    def migrate_to_themed_bodies(self, connection: sqlite3.Connection) -> None:
        """Markdown drafts used to store a whole document; they now store a body fragment.

        Legacy rows are relabelled as html so they keep being served verbatim rather than
        being double-wrapped in a fresh shell. They expire on their original schedule.
        """
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(drafts)")}
        if "theme" in columns:
            return
        connection.execute("ALTER TABLE drafts ADD COLUMN theme TEXT")
        connection.execute("UPDATE drafts SET source_format = 'html' WHERE source_format = 'markdown'")

    def insert(self, draft: Draft) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO drafts (
                    id, title, filename, source_format, theme,
                    created_at, expires_at, size_bytes, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.id,
                    draft.title,
                    draft.filename,
                    draft.source_format,
                    draft.theme,
                    draft.created_at,
                    draft.expires_at,
                    draft.size_bytes,
                    draft.content_hash,
                ),
            )

    def find_live(self, draft_id: str, now: int) -> Draft | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM drafts WHERE id = ? AND expires_at > ?", (draft_id, now)
            ).fetchone()
        return Draft(**row) if row else None

    def list_live(self, now: int) -> list[Draft]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM drafts WHERE expires_at > ? ORDER BY created_at DESC", (now,)
            ).fetchall()
        return [Draft(**row) for row in rows]

    def all_ids(self) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute("SELECT id FROM drafts").fetchall()
        return {row["id"] for row in rows}

    def delete(self, draft_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
        return cursor.rowcount > 0

    def take_expired_ids(self, now: int) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "DELETE FROM drafts WHERE expires_at <= ? RETURNING id", (now,)
            ).fetchall()
        return [row["id"] for row in rows]
