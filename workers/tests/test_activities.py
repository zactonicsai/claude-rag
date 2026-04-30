"""Activity tests — make_activities() returns sync callables; we exercise them
directly with mocked external services. No live S3 / Chroma / Tesseract needed.
"""
import base64
import sqlite3
import time
from unittest.mock import patch, MagicMock

import pytest

from shared.activities import (
    make_activities, FetchInput, FetchResult, ConvertInput, IngestInput,
)
from shared.config import WorkerConfig


_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY, filename TEXT NOT NULL, content_type TEXT,
    size_bytes INTEGER DEFAULT 0, s3_key TEXT NOT NULL, status TEXT NOT NULL,
    error TEXT, extracted_chars INTEGER DEFAULT 0, chunk_count INTEGER DEFAULT 0,
    extracted_text TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
    workflow_id TEXT
);
"""


@pytest.fixture
def cfg(tmp_path):
    db = str(tmp_path / "files.db")
    conn = sqlite3.connect(db)
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
    return WorkerConfig(
        role="ingest",
        chroma_host="x", chroma_port=8000, chroma_collection="c",
        s3_endpoint="http://x", s3_bucket="b",
        aws_access_key_id="k", aws_secret_access_key="s",
        aws_default_region="us-east-1",
        temporal_host="x:7233", temporal_namespace="default",
        task_queue_main="m", task_queue_doc="d",
        task_queue_ocr="o", task_queue_ingest="i",
        db_path=db, chunk_size=80, chunk_overlap=10,
    )


def test_fetch_from_s3(cfg):
    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"hello bytes")}
    fake_s3.head_object.return_value = {"ContentType": "text/plain"}

    with patch("shared.activities._s3_client", return_value=fake_s3):
        acts = make_activities(cfg)
        out: FetchResult = acts["fetch_from_s3"](
            FetchInput(file_id="f1", s3_key="uploads/f1/doc.txt")
        )

    assert out.file_id == "f1"
    assert out.filename == "doc.txt"
    assert out.content_type == "text/plain"
    assert out.size_bytes == 11
    assert base64.b64decode(out.body_b64) == b"hello bytes"


def test_detect_kind(cfg):
    acts = make_activities(cfg)
    txt = FetchResult(file_id="f1", filename="doc.txt", content_type="text/plain",
                      size_bytes=10, body_b64="")
    img = FetchResult(file_id="f2", filename="scan.png", content_type="image/png",
                      size_bytes=10, body_b64="")
    assert acts["detect_kind"](txt) == "doc"
    assert acts["detect_kind"](img) == "image"


def test_convert_doc_writes_extracted_text(cfg):
    acts = make_activities(cfg)
    body = base64.b64encode(b"line one\nline two").decode()
    inp = ConvertInput(file_id="f1", filename="notes.txt",
                       content_type="text/plain", body_b64=body)
    out = acts["convert_doc"](inp)
    assert out.chars > 0
    assert "line one" in out.text
    # And the DB should now have the extracted text + status=converting
    conn = sqlite3.connect(cfg.db_path)
    row = conn.execute(
        "SELECT status, extracted_text, extracted_chars FROM files WHERE id='f1'"
    ).fetchone()
    assert row[0] == "converting"
    assert "line one" in row[1]
    assert row[2] == out.chars


def test_ocr_image_uses_pytesseract(cfg):
    acts = make_activities(cfg)
    body = base64.b64encode(b"fake-image-bytes").decode()
    inp = ConvertInput(file_id="f1", filename="scan.png",
                       content_type="image/png", body_b64=body)

    fake_img = MagicMock()
    with patch("PIL.Image.open", return_value=fake_img) as pimg, \
         patch("pytesseract.image_to_string", return_value="OCR'd text") as pocr:
        out = acts["ocr_image"](inp)

    pimg.assert_called_once()
    pocr.assert_called_once_with(fake_img)
    assert out.text == "OCR'd text"
    # DB updated
    conn = sqlite3.connect(cfg.db_path)
    row = conn.execute(
        "SELECT status, extracted_text FROM files WHERE id='f1'"
    ).fetchone()
    assert row[0] == "ocr"
    assert row[1] == "OCR'd text"


def test_chunk_and_embed_writes_to_chroma(cfg):
    # Pre-populate the extracted text the activity will read.
    conn = sqlite3.connect(cfg.db_path)
    text = ". ".join(f"sentence {i} with content" for i in range(40))
    conn.execute(
        "UPDATE files SET extracted_text=?, extracted_chars=? WHERE id='f1'",
        (text, len(text)),
    )
    conn.commit()
    conn.close()

    fake_collection = MagicMock()
    fake_client = MagicMock()
    fake_client.get_or_create_collection.return_value = fake_collection

    with patch("chromadb.HttpClient", return_value=fake_client):
        acts = make_activities(cfg)
        out = acts["chunk_and_embed"](IngestInput(file_id="f1", filename="doc.txt"))

    assert out.chunk_count > 0
    # Chroma `add` was called at least once with matching metadata
    assert fake_collection.add.call_count >= 1
    first_call_kwargs = fake_collection.add.call_args_list[0].kwargs
    assert all(m["file_id"] == "f1" for m in first_call_kwargs["metadatas"])
    assert all(m["filename"] == "doc.txt" for m in first_call_kwargs["metadatas"])
    # DB chunk_count should match
    conn = sqlite3.connect(cfg.db_path)
    n = conn.execute("SELECT chunk_count FROM files WHERE id='f1'").fetchone()[0]
    assert n == out.chunk_count


def test_chunk_and_embed_handles_empty_text(cfg):
    fake_collection = MagicMock()
    fake_client = MagicMock()
    fake_client.get_or_create_collection.return_value = fake_collection

    with patch("chromadb.HttpClient", return_value=fake_client):
        acts = make_activities(cfg)
        out = acts["chunk_and_embed"](IngestInput(file_id="f1", filename="doc.txt"))

    assert out.chunk_count == 0
    fake_collection.add.assert_not_called()


def test_mark_status(cfg):
    acts = make_activities(cfg)
    acts["mark_status"]({"file_id": "f1", "status": "ready"})
    conn = sqlite3.connect(cfg.db_path)
    row = conn.execute("SELECT status FROM files WHERE id='f1'").fetchone()
    assert row[0] == "ready"

    acts["mark_status"]({"file_id": "f1", "status": "error", "error": "kaboom"})
    conn = sqlite3.connect(cfg.db_path)
    row = conn.execute(
        "SELECT status, error FROM files WHERE id='f1'"
    ).fetchone()
    assert row == ("error", "kaboom")
