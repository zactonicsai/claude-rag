from shared.chunking import chunk_text


def test_empty():
    assert chunk_text("") == []


def test_short():
    out = chunk_text("Hello world. Goodnight.", chunk_size=200)
    assert out == ["Hello world. Goodnight."]


def test_window_split():
    text = ". ".join(f"sentence {i}" for i in range(80))
    chunks = chunk_text(text, chunk_size=120, overlap=30)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 120 + 40
