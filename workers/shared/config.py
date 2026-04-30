"""Shared worker configuration loaded from env."""
from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass
class WorkerConfig:
    role: str  # doc | ocr | ingest

    chroma_host: str
    chroma_port: int
    chroma_collection: str

    s3_endpoint: str
    s3_bucket: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_default_region: str

    temporal_host: str
    temporal_namespace: str

    task_queue_main: str
    task_queue_doc: str
    task_queue_ocr: str
    task_queue_ingest: str

    db_path: str
    chunk_size: int
    chunk_overlap: int

    @staticmethod
    def from_env() -> "WorkerConfig":
        return WorkerConfig(
            role=os.getenv("WORKER_ROLE", "doc"),
            chroma_host=os.getenv("CHROMA_HOST", "chromadb"),
            chroma_port=int(os.getenv("CHROMA_PORT", "8000")),
            chroma_collection=os.getenv("CHROMA_COLLECTION", "rag_documents"),
            s3_endpoint=os.getenv("S3_ENDPOINT", "http://localstack:4566"),
            s3_bucket=os.getenv("S3_BUCKET", "rag-uploads"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
            aws_default_region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            temporal_host=os.getenv("TEMPORAL_HOST", "temporal:7233"),
            temporal_namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
            task_queue_main=os.getenv("TQ_MAIN", "file-processing"),
            task_queue_doc=os.getenv("TQ_DOC", "doc-conversion"),
            task_queue_ocr=os.getenv("TQ_OCR", "ocr-processing"),
            task_queue_ingest=os.getenv("TQ_INGEST", "chroma-ingestion"),
            db_path=os.getenv("DB_PATH", "/data/files.db"),
            chunk_size=int(os.getenv("CHUNK_SIZE", "1200")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "150")),
        )
