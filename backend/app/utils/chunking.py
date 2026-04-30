"""Token-aware-ish text chunking.

We don't pull in a tokenizer just for this — a character-window approximation
with sentence-friendly break points works fine for embedding purposes and
keeps the dependency surface small. `chunk_size` is in characters.
"""
from __future__ import annotations
import re

_BREAK = re.compile(r"(?<=[\.\!\?\n])\s+")


def chunk_text(text: str, chunk_size: int = 1200,
               overlap: int = 150) -> list[str]:
    """Split `text` into overlapping windows roughly of `chunk_size` chars.

    Tries to break on sentence boundaries; falls back to hard splits if a
    single "sentence" exceeds the window.
    """
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    overlap = max(0, min(overlap, chunk_size // 2))

    # Pre-split into sentence-ish units so we don't break mid-sentence.
    sentences = [s for s in _BREAK.split(text.strip()) if s]

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def flush():
        nonlocal buf, buf_len
        if buf:
            chunks.append(" ".join(buf).strip())
            buf, buf_len = [], 0

    for sent in sentences:
        # If a single sentence is itself larger than the window, hard-split.
        if len(sent) > chunk_size:
            flush()
            for i in range(0, len(sent), chunk_size - overlap):
                chunks.append(sent[i:i + chunk_size].strip())
            continue

        if buf_len + len(sent) + 1 > chunk_size:
            flush()
            # carry overlap from previous chunk
            if overlap and chunks:
                tail = chunks[-1][-overlap:]
                buf.append(tail)
                buf_len = len(tail)
        buf.append(sent)
        buf_len += len(sent) + 1

    flush()
    return [c for c in chunks if c]
