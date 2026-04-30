"""Unit tests for the chunker."""
from app.utils.chunking import chunk_text


def test_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_text_single_chunk():
    out = chunk_text("Hello there. This is a quick test.", chunk_size=200)
    assert len(out) == 1
    assert "Hello there" in out[0]


def test_chunks_respect_size():
    text = ". ".join(f"Sentence number {i} with some padding text" for i in range(200))
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    assert len(chunks) > 1
    # No chunk should be much bigger than chunk_size + overlap window.
    for c in chunks:
        assert len(c) <= 300 + 60  # slop for sentence boundary


def test_overlap_provides_continuity():
    text = ". ".join(f"alpha{i} beta{i} gamma{i}" for i in range(50))
    chunks = chunk_text(text, chunk_size=120, overlap=40)
    assert len(chunks) >= 2
    # adjacent chunks should share *some* content via overlap
    overlap_seen = any(
        chunks[i][-20:] in chunks[i + 1] or chunks[i + 1][:40] in chunks[i]
        for i in range(len(chunks) - 1)
    )
    assert overlap_seen or len(chunks) <= 2


def test_huge_single_sentence_is_hard_split():
    huge = "a" * 5000
    chunks = chunk_text(huge, chunk_size=500, overlap=50)
    assert len(chunks) > 1
    # Every chunk should be at most chunk_size chars.
    for c in chunks:
        assert len(c) <= 500


def test_invalid_chunk_size():
    import pytest
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=0)
