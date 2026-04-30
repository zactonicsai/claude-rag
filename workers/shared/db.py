"""Tiny worker-side SQLite helpers — same DB file the backend writes to.

Kept dependency-free (just stdlib) so the doc/ocr workers don't need pydantic.
"""
from __future__ import annotations
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator, Optional


@contextmanager
def _conn(path: str) -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    try:
        yield conn
    finally:
        conn.close()


def update_status(db_path: str, file_id: str, status: str,
                  error: Optional[str] = None) -> None:
    with _conn(db_path) as c:
        c.execute(
            "UPDATE files SET status=?, error=?, updated_at=? WHERE id=?",
            (status, error, time.time(), file_id),
        )


def set_extracted_text(db_path: str, file_id: str, text: str) -> None:
    with _conn(db_path) as c:
        c.execute(
            """UPDATE files SET extracted_text=?, extracted_chars=?,
                                updated_at=? WHERE id=?""",
            (text, len(text), time.time(), file_id),
        )


def set_chunks(db_path: str, file_id: str, n_chunks: int) -> None:
    with _conn(db_path) as c:
        c.execute(
            "UPDATE files SET chunk_count=?, updated_at=? WHERE id=?",
            (n_chunks, time.time(), file_id),
        )


def get_extracted_text(db_path: str, file_id: str) -> Optional[str]:
    with _conn(db_path) as c:
        row = c.execute(
            "SELECT extracted_text FROM files WHERE id=?", (file_id,)
        ).fetchone()
    return row["extracted_text"] if row else None


def get_filename(db_path: str, file_id: str) -> Optional[str]:
    with _conn(db_path) as c:
        row = c.execute(
            "SELECT filename FROM files WHERE id=?", (file_id,)
        ).fetchone()
    return row["filename"] if row else None
