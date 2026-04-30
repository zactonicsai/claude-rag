"""Files route tests — S3 + Temporal mocked out."""
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "files.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")

    from app.config import get_settings
    get_settings.cache_clear()

    from app.main import app
    return TestClient(app)


def test_upload_kicks_off_workflow(client):
    fake_s3 = MagicMock()
    fake_temporal = AsyncMock()
    fake_temporal.start_workflow = AsyncMock()

    with patch("app.routes.files.make_s3_client", return_value=fake_s3), \
         patch("app.routes.files.ensure_bucket"), \
         patch("app.routes.files.temporal_connect_with_retry",
               new=AsyncMock(return_value=fake_temporal)):
        r = client.post(
            "/api/files/upload",
            files={"file": ("hello.txt", b"hello world", "text/plain")},
        )

    assert r.status_code == 202, r.text
    body = r.json()
    assert "file_id" in body and "workflow_id" in body
    fake_s3.put_object.assert_called_once()
    fake_temporal.start_workflow.assert_awaited_once()


def test_list_files_empty(client):
    r = client.get("/api/files")
    assert r.status_code == 200
    assert r.json() == {"files": []}


def test_get_file_404(client):
    r = client.get("/api/files/nope")
    assert r.status_code == 404


def test_list_after_upload(client):
    fake_s3 = MagicMock()
    fake_temporal = AsyncMock()
    fake_temporal.start_workflow = AsyncMock()

    with patch("app.routes.files.make_s3_client", return_value=fake_s3), \
         patch("app.routes.files.ensure_bucket"), \
         patch("app.routes.files.temporal_connect_with_retry",
               new=AsyncMock(return_value=fake_temporal)):
        client.post("/api/files/upload",
                    files={"file": ("a.txt", b"abc", "text/plain")})

    r = client.get("/api/files")
    assert r.status_code == 200
    files = r.json()["files"]
    assert len(files) == 1
    assert files[0]["filename"] == "a.txt"
    assert files[0]["status"] == "pending"


def test_get_text_for_unknown_file(client):
    r = client.get("/api/files/nope/text")
    assert r.status_code == 404


def test_workflow_start_failure_marks_error(client):
    fake_s3 = MagicMock()
    with patch("app.routes.files.make_s3_client", return_value=fake_s3), \
         patch("app.routes.files.ensure_bucket"), \
         patch("app.routes.files.temporal_connect_with_retry",
               new=AsyncMock(side_effect=RuntimeError("temporal down"))):
        r = client.post("/api/files/upload",
                        files={"file": ("x.txt", b"data", "text/plain")})
    assert r.status_code == 500

    # The file should be persisted with status='error' so the user can see it.
    files = client.get("/api/files").json()["files"]
    assert len(files) == 1
    assert files[0]["status"] == "error"
    assert "temporal down" in (files[0]["error"] or "")


def test_delete_file(client):
    # Insert a file via upload.
    fake_s3 = MagicMock()
    fake_temporal = AsyncMock()
    fake_temporal.start_workflow = AsyncMock()
    with patch("app.routes.files.make_s3_client", return_value=fake_s3), \
         patch("app.routes.files.ensure_bucket"), \
         patch("app.routes.files.temporal_connect_with_retry",
               new=AsyncMock(return_value=fake_temporal)):
        up = client.post("/api/files/upload",
                         files={"file": ("a.txt", b"abc", "text/plain")})
    fid = up.json()["file_id"]

    with patch("app.routes.files.make_s3_client", return_value=fake_s3), \
         patch("app.routes.files.make_chroma_client", return_value=MagicMock()), \
         patch("app.routes.files.get_or_create_collection", return_value=MagicMock()), \
         patch("app.routes.files.delete_by_file"):
        r = client.delete(f"/api/files/{fid}")
    assert r.status_code == 204
    assert client.get(f"/api/files/{fid}").status_code == 404
