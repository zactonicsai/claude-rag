"""Worker DB tests — exercise the worker-side updates against a tmp SQLite."""
import sqlite3
import time

import pytest

from shared import db as worker_db


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


@pytest.fixture
def db_path(tmp_path):
    p = str(tmp_path / "files.db")
    conn = sqlite3.connect(p)
    conn.executescript(_SCHEMA)
    now = time.time()
    conn.execute(
        """INSERT INTO files (id, filename, s3_key, status,
                              created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("f1", "doc.txt", "uploads/f1/doc.txt", "pending", now, now),
    )
    conn.commit()
    conn.close()
    return p


def test_update_status(db_path):
    worker_db.update_status(db_path, "f1", "ready")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status FROM files WHERE id='f1'").fetchone()
    assert row[0] == "ready"


def test_update_status_with_error(db_path):
    worker_db.update_status(db_path, "f1", "error", error="boom")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status, error FROM files WHERE id='f1'").fetchone()
    assert row == ("error", "boom")


def test_set_extracted_text(db_path):
    worker_db.set_extracted_text(db_path, "f1", "hello world")
    assert worker_db.get_extracted_text(db_path, "f1") == "hello world"
    conn = sqlite3.connect(db_path)
    chars = conn.execute(
        "SELECT extracted_chars FROM files WHERE id='f1'"
    ).fetchone()[0]
    assert chars == 11


def test_set_chunks(db_path):
    worker_db.set_chunks(db_path, "f1", 12)
    conn = sqlite3.connect(db_path)
    n = conn.execute(
        "SELECT chunk_count FROM files WHERE id='f1'"
    ).fetchone()[0]
    assert n == 12


def test_get_filename(db_path):
    assert worker_db.get_filename(db_path, "f1") == "doc.txt"
    assert worker_db.get_filename(db_path, "missing") is None
