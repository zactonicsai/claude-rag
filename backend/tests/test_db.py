"""Unit tests for the FileDB SQLite registry."""
import os
import time

import pytest

from app.db import FileDB
from app.models import FileRecord


@pytest.fixture
def db(tmp_path):
    return FileDB(str(tmp_path / "files.db"))


def _rec(file_id="f1", **overrides):
    base = dict(
        id=file_id, filename="hello.txt", content_type="text/plain",
        size_bytes=11, s3_key=f"uploads/{file_id}/hello.txt",
        status="pending", created_at=time.time(), updated_at=time.time(),
        workflow_id=f"wf-{file_id}",
    )
    base.update(overrides)
    return FileRecord(**base)


def test_insert_and_get(db):
    db.insert(_rec("f1"))
    got = db.get("f1")
    assert got is not None
    assert got.filename == "hello.txt"
    assert got.status == "pending"


def test_update_status(db):
    db.insert(_rec("f1"))
    db.update_status("f1", "ready")
    assert db.get("f1").status == "ready"
    db.update_status("f1", "error", error="boom")
    rec = db.get("f1")
    assert rec.status == "error"
    assert rec.error == "boom"


def test_set_extracted_and_chunks(db):
    db.insert(_rec("f1"))
    db.set_extracted("f1", "hello world")
    db.set_chunks("f1", 7)
    rec = db.get("f1")
    assert rec.extracted_chars == 11
    assert rec.chunk_count == 7
    assert db.get_text("f1") == "hello world"


def test_list_orders_by_created_desc(db):
    db.insert(_rec("a", created_at=1.0, updated_at=1.0))
    db.insert(_rec("b", created_at=2.0, updated_at=2.0))
    ids = [r.id for r in db.list_all()]
    assert ids == ["b", "a"]


def test_delete(db):
    db.insert(_rec("f1"))
    db.delete("f1")
    assert db.get("f1") is None


def test_get_missing(db):
    assert db.get("nope") is None
    assert db.get_text("nope") is None
