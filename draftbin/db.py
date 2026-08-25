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

-- Records that an id once existed and when it stopped resolving, so a stale link can
-- say "this expired" instead of being indistinguishable from a typo. Content is never
-- kept here; the row is an id and a timestamp.
CREATE TABLE IF NOT EXISTS tombstones (
    id         TEXT PRIMARY KEY,
    removed_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS tombstones_removed_at ON tombstones (removed_at);
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

    def replace(self, draft: Draft) -> None:
        """Everything but the id and the original publication date is overwritten."""
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE drafts SET
                    title = ?, filename = ?, source_format = ?, theme = ?,
                    expires_at = ?, size_bytes = ?, content_hash = ?
                WHERE id = ?
                """,
                (
                    draft.title,
                    draft.filename,
                    draft.source_format,
                    draft.theme,
                    draft.expires_at,
                    draft.size_bytes,
                    draft.content_hash,
                    draft.id,
                ),
            )

    def set_expiry(self, draft_id: str, expires_at: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE drafts SET expires_at = ? WHERE id = ?", (expires_at, draft_id)
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

    def id_in_use(self, draft_id: str) -> bool:
        """Tombstones count as in use, so an id is never handed out twice.

        Reissuing one would silently point a link somebody still holds at unrelated
        content. Only matters now that ids are short enough to collide at all.
        """
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM drafts WHERE id = ?
                UNION ALL
                SELECT 1 FROM tombstones WHERE id = ?
                LIMIT 1
                """,
                (draft_id, draft_id),
            ).fetchone()
        return row is not None

    def all_ids(self) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute("SELECT id FROM drafts").fetchall()
        return {row["id"] for row in rows}

    def delete(self, draft_id: str, now: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
            if cursor.rowcount:
                self.entomb(connection, [draft_id], now)
        return cursor.rowcount > 0

    def take_expired_ids(self, now: int) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "DELETE FROM drafts WHERE expires_at <= ? RETURNING id", (now,)
            ).fetchall()
            expired = [row["id"] for row in rows]
            self.entomb(connection, expired, now)
        return expired

    def entomb(self, connection: sqlite3.Connection, draft_ids: list[str], now: int) -> None:
        connection.executemany(
            "INSERT OR REPLACE INTO tombstones (id, removed_at) VALUES (?, ?)",
            [(draft_id, now) for draft_id in draft_ids],
        )

    def removed_at(self, draft_id: str, now: int) -> int | None:
        """When an id stopped resolving, whether the sweeper has reached it yet or not.

        Expiry is enforced at read time, so a row can be past its date and still present.
        """
        with self.connect() as connection:
            lapsed = connection.execute(
                "SELECT expires_at FROM drafts WHERE id = ? AND expires_at <= ?", (draft_id, now)
            ).fetchone()
            if lapsed:
                return lapsed["expires_at"]
            tombstone = connection.execute(
                "SELECT removed_at FROM tombstones WHERE id = ?", (draft_id,)
            ).fetchone()
        return tombstone["removed_at"] if tombstone else None

    def purge_tombstones(self, before: int) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM tombstones WHERE removed_at <= ?", (before,)
            )
        return cursor.rowcount
