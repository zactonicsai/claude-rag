"""Chat route tests — Chroma + Claude are stubbed out."""
import os
from unittest.mock import patch, MagicMock

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


def _fake_chroma_results(chunks):
    coll = MagicMock()
    if chunks:
        coll.query.return_value = {
            "ids": [[f"id{i}" for i in range(len(chunks))]],
            "documents": [[c["text"] for c in chunks]],
            "metadatas": [[{"file_id": c["file_id"], "filename": c["filename"]} for c in chunks]],
            "distances": [[c.get("distance", 0.1) for c in chunks]],
        }
    else:
        coll.query.return_value = {
            "ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]],
        }
    return coll


def test_chroma_only_returns_chunks_no_claude(client):
    fake_chunks = [
        {"file_id": "f1", "filename": "a.txt", "text": "alpha content", "distance": 0.1},
        {"file_id": "f1", "filename": "a.txt", "text": "beta content", "distance": 0.2},
    ]
    fake_collection = _fake_chroma_results(fake_chunks)

    with patch("app.routes.chat.make_chroma_client") as mk_chroma, \
         patch("app.routes.chat.get_or_create_collection", return_value=fake_collection):
        mk_chroma.return_value = MagicMock()

        r = client.post("/api/chat", json={
            "message": "what is alpha?",
            "file_ids": [],
            "chroma_only": True,
        })

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["used_chroma_only"] is True
    assert len(data["chunks"]) == 2
    assert data["cost"]["total_cost_usd"] == 0.0
    assert "alpha content" in data["answer"]


def test_chroma_only_no_chunks_message(client):
    fake_collection = _fake_chroma_results([])
    with patch("app.routes.chat.make_chroma_client", return_value=MagicMock()), \
         patch("app.routes.chat.get_or_create_collection", return_value=fake_collection):
        r = client.post("/api/chat", json={
            "message": "anything",
            "chroma_only": True,
        })
    assert r.status_code == 200
    assert "No matching context" in r.json()["answer"]


def test_full_chat_calls_claude_and_computes_cost(client):
    fake_chunks = [
        {"file_id": "f1", "filename": "doc.md", "text": "the answer is 42", "distance": 0.1},
    ]
    fake_collection = _fake_chroma_results(fake_chunks)

    fake_claude_result = MagicMock()
    fake_claude_result.text = "It is 42 [doc.md]."
    fake_claude_result.input_tokens = 1000
    fake_claude_result.output_tokens = 200
    fake_claude_result.model = "claude-test"

    with patch("app.routes.chat.make_chroma_client", return_value=MagicMock()), \
         patch("app.routes.chat.get_or_create_collection", return_value=fake_collection), \
         patch("app.routes.chat.ClaudeClient") as ClaudeCls:
        instance = ClaudeCls.return_value
        instance.chat.return_value = fake_claude_result
        # cost_for: 1k input @ $3/M = 0.003 ; 200 output @ $15/M = 0.003 ; total = 0.006
        instance.cost_for.return_value = (0.003, 0.003, 0.006)

        r = client.post("/api/chat", json={
            "message": "answer please",
            "file_ids": ["f1"],
            "chroma_only": False,
        })

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["used_chroma_only"] is False
    assert data["answer"] == "It is 42 [doc.md]."
    assert data["cost"]["input_tokens"] == 1000
    assert data["cost"]["output_tokens"] == 200
    assert data["cost"]["total_cost_usd"] == pytest.approx(0.006)
    assert data["cost"]["model"] == "claude-test"


def test_chat_validation_empty_message(client):
    r = client.post("/api/chat", json={"message": ""})
    assert r.status_code == 422


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
