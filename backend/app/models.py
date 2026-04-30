"""API request/response models."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class FileRecord(BaseModel):
    id: str
    filename: str
    content_type: Optional[str] = None
    size_bytes: int = 0
    s3_key: str
    status: str  # pending|converting|ocr|chunking|ready|error
    error: Optional[str] = None
    extracted_chars: int = 0
    chunk_count: int = 0
    created_at: float
    updated_at: float
    workflow_id: Optional[str] = None


class FileListResponse(BaseModel):
    files: list[FileRecord]


class ExtractedTextResponse(BaseModel):
    file_id: str
    filename: str
    text: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    file_ids: list[str] = Field(default_factory=list)
    chroma_only: bool = False


class CostBreakdown(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    model: Optional[str] = None


class ContextChunk(BaseModel):
    file_id: str
    filename: str
    text: str
    distance: Optional[float] = None


class ChatResponse(BaseModel):
    answer: str
    used_chroma_only: bool
    chunks: list[ContextChunk]
    cost: CostBreakdown
