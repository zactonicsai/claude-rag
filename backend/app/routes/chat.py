"""Chat route.

Workflow per request:
  1. Embed the user message (via Chroma) and pull top-k chunks, optionally
     filtered to a user-selected subset of file_ids.
  2. If `chroma_only=True` → return the chunks verbatim, no Claude call,
     cost = $0.
  3. Otherwise → assemble a system prompt with the retrieved context,
     call Claude, return answer + token/cost breakdown.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings, get_settings
from ..models import (
    ChatRequest, ChatResponse, ContextChunk, CostBreakdown,
)
from ..chroma_client import make_chroma_client, get_or_create_collection, query_collection
from ..claude_client import ClaudeClient

router = APIRouter(prefix="/api/chat", tags=["chat"])


_SYSTEM_PROMPT = """You are a careful, concise assistant. Answer the user's
question using the supplied context when it's relevant. If the context does
not contain the answer, say so plainly and answer from general knowledge,
clearly marking which parts come from context vs. general knowledge.
Cite context snippets inline as [filename] when you use them."""


def _format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "(no retrieved context)"
    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(
            f"--- Chunk {i} (file: {c['filename']}) ---\n{c['text']}"
        )
    return "\n\n".join(parts)


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest, settings: Settings = Depends(get_settings)):
    # ── 1. Retrieval ─────────────────────────────────────────────────────
    try:
        chroma = make_chroma_client(settings.chroma_host, settings.chroma_port)
        coll = get_or_create_collection(chroma, settings.chroma_collection)
        raw = query_collection(
            coll, req.message, top_k=settings.top_k,
            file_ids=req.file_ids or None,
        )
    except Exception as e:
        raise HTTPException(500, f"chroma query failed: {e}")

    chunks = [
        ContextChunk(
            file_id=r["file_id"], filename=r["filename"],
            text=r["text"], distance=r["distance"],
        )
        for r in raw
    ]

    # ── 2. Chroma-only mode — no Claude call ─────────────────────────────
    if req.chroma_only:
        if not chunks:
            answer = (
                "No matching context was found in the document store. "
                "Upload some files or uncheck 'ChromaDB only' to ask Claude."
            )
        else:
            answer = "Top retrieved passages:\n\n" + "\n\n".join(
                f"• [{c.filename}] {c.text}" for c in chunks
            )
        return ChatResponse(
            answer=answer, used_chroma_only=True, chunks=chunks,
            cost=CostBreakdown(model=None),
        )

    # ── 3. Claude call ───────────────────────────────────────────────────
    if not settings.anthropic_api_key or settings.anthropic_api_key.startswith("sk-ant-missing"):
        raise HTTPException(
            500, "ANTHROPIC_API_KEY is not configured on the server",
        )

    claude = ClaudeClient(
        api_key=settings.anthropic_api_key,
        model=settings.claude_model,
        price_in_per_mtok=settings.claude_price_input_per_mtok,
        price_out_per_mtok=settings.claude_price_output_per_mtok,
        max_output_tokens=settings.max_output_tokens,
    )

    user_prompt = (
        f"# Context\n{_format_context(raw)}\n\n"
        f"# Question\n{req.message}"
    )
    try:
        result = claude.chat(system=_SYSTEM_PROMPT, user_message=user_prompt)
    except Exception as e:
        raise HTTPException(502, f"Claude API call failed: {e}")

    ic, oc, tot = claude.cost_for(result.input_tokens, result.output_tokens)
    return ChatResponse(
        answer=result.text,
        used_chroma_only=False,
        chunks=chunks,
        cost=CostBreakdown(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            input_cost_usd=round(ic, 6),
            output_cost_usd=round(oc, 6),
            total_cost_usd=round(tot, 6),
            model=result.model,
        ),
    )
