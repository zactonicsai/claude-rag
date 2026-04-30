"""Tiny SQLite-backed registry of uploaded files and their processing state.

Used by the API and by workers (workers update status via the same DB file
mounted into all containers via the shared `backend-data` volume).
"""
from __future__ import annotations
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from .models import FileRecord


_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id              TEXT PRIMARY KEY,
    filename        TEXT NOT NULL,
    content_type    TEXT,
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    s3_key          TEXT NOT NULL,
    status          TEXT NOT NULL,
    error           TEXT,
    extracted_chars INTEGER NOT NULL DEFAULT 0,
    chunk_count     INTEGER NOT NULL DEFAULT 0,
    extracted_text  TEXT,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    workflow_id     TEXT
);
"""


class FileDB:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        try:
            yield conn
        finally:
            conn.close()

    # ── writes ──────────────────────────────────────────────────────────
    def insert(self, rec: FileRecord) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO files (id, filename, content_type, size_bytes,
                                      s3_key, status, error, extracted_chars,
                                      chunk_count, created_at, updated_at,
                                      workflow_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rec.id, rec.filename, rec.content_type, rec.size_bytes,
                 rec.s3_key, rec.status, rec.error, rec.extracted_chars,
                 rec.chunk_count, rec.created_at, rec.updated_at,
                 rec.workflow_id),
            )

    def update_status(self, file_id: str, status: str,
                      error: Optional[str] = None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE files SET status=?, error=?, updated_at=? WHERE id=?",
                (status, error, time.time(), file_id),
            )

    def set_extracted(self, file_id: str, text: str) -> None:
        with self._conn() as c:
            c.execute(
                """UPDATE files SET extracted_text=?, extracted_chars=?,
                                    updated_at=? WHERE id=?""",
                (text, len(text), time.time(), file_id),
            )

    def set_chunks(self, file_id: str, chunk_count: int) -> None:
        with self._conn() as c:
            c.execute(
                """UPDATE files SET chunk_count=?, updated_at=? WHERE id=?""",
                (chunk_count, time.time(), file_id),
            )

    def delete(self, file_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM files WHERE id=?", (file_id,))

    # ── reads ───────────────────────────────────────────────────────────
    def get(self, file_id: str) -> Optional[FileRecord]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM files WHERE id=?", (file_id,)
            ).fetchone()
        return _row_to_record(row) if row else None

    def get_text(self, file_id: str) -> Optional[str]:
        with self._conn() as c:
            row = c.execute(
                "SELECT extracted_text FROM files WHERE id=?", (file_id,)
            ).fetchone()
        return row["extracted_text"] if row else None

    def list_all(self) -> list[FileRecord]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM files ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_record(r) for r in rows]


def _row_to_record(row: sqlite3.Row) -> FileRecord:
    return FileRecord(
        id=row["id"],
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"] or 0,
        s3_key=row["s3_key"],
        status=row["status"],
        error=row["error"],
        extracted_chars=row["extracted_chars"] or 0,
        chunk_count=row["chunk_count"] or 0,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        workflow_id=row["workflow_id"],
    )
