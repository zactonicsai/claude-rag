"""Chunking — kept in sync with backend/app/utils/chunking.py."""
from __future__ import annotations
import re

_BREAK = re.compile(r"(?<=[\.\!\?\n])\s+")


def chunk_text(text: str, chunk_size: int = 1200,
               overlap: int = 150) -> list[str]:
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    overlap = max(0, min(overlap, chunk_size // 2))
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
        if len(sent) > chunk_size:
            flush()
            for i in range(0, len(sent), chunk_size - overlap):
                chunks.append(sent[i:i + chunk_size].strip())
            continue

        if buf_len + len(sent) + 1 > chunk_size:
            flush()
            if overlap and chunks:
                tail = chunks[-1][-overlap:]
                buf.append(tail)
                buf_len = len(tail)
        buf.append(sent)
        buf_len += len(sent) + 1

    flush()
    return [c for c in chunks if c]
