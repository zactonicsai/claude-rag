"""Centralized settings sourced from environment variables."""
from __future__ import annotations
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str = "sk-ant-missing"
    claude_model: str = "claude-sonnet-4-5"
    claude_price_input_per_mtok: float = 3.00
    claude_price_output_per_mtok: float = 15.00
    max_output_tokens: int = 1024

    # ChromaDB
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    chroma_collection: str = "rag_documents"

    # S3 / LocalStack
    s3_endpoint: str = "http://localstack:4566"
    s3_bucket: str = "rag-uploads"
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
    aws_default_region: str = "us-east-1"

    # Temporal
    temporal_host: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_task_queue_main: str = "file-processing"
    temporal_task_queue_doc: str = "doc-conversion"
    temporal_task_queue_ocr: str = "ocr-processing"
    temporal_task_queue_ingest: str = "chroma-ingestion"

    # Files DB
    db_path: str = "/data/files.db"

    # Chunking / retrieval
    chunk_size: int = 1200
    chunk_overlap: int = 150
    top_k: int = 6

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
