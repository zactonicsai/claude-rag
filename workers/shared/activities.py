"""Temporal activities — units of work the workflow can dispatch.

Each activity is intentionally narrow so it can be hosted on whichever worker
has the right dependencies installed (OCR activities live on a worker that
ships tesseract, doc activities on one that ships pypdf/python-docx, etc.).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from temporalio import activity

from .config import WorkerConfig
from . import db as worker_db
from . import chunking
from . import converters


# ─── inputs / outputs ──────────────────────────────────────────────────────
@dataclass
class FetchInput:
    file_id: str
    s3_key: str


@dataclass
class FetchResult:
    file_id: str
    filename: str
    content_type: str
    size_bytes: int
    # bytes are returned base64-encoded so they survive Temporal payload codecs
    body_b64: str


@dataclass
class ConvertInput:
    file_id: str
    filename: str
    content_type: str
    body_b64: str


@dataclass
class ConvertResult:
    file_id: str
    text: str
    chars: int


@dataclass
class IngestInput:
    file_id: str
    filename: str


@dataclass
class IngestResult:
    file_id: str
    chunk_count: int


# ─── helpers ───────────────────────────────────────────────────────────────
def _s3_client(cfg: WorkerConfig):
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url=cfg.s3_endpoint,
        region_name=cfg.aws_default_region,
        aws_access_key_id=cfg.aws_access_key_id,
        aws_secret_access_key=cfg.aws_secret_access_key,
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
    )


# ─── activities (all sync; Temporal runs them on a thread pool) ────────────
def make_activities(cfg: WorkerConfig):
    """Closure-based factory so activities can capture worker config."""

    @activity.defn(name="fetch_from_s3")
    def fetch_from_s3(inp: FetchInput) -> FetchResult:
        import base64
        s3 = _s3_client(cfg)
        obj = s3.get_object(Bucket=cfg.s3_bucket, Key=inp.s3_key)
        body = obj["Body"].read()
        head = s3.head_object(Bucket=cfg.s3_bucket, Key=inp.s3_key)
        return FetchResult(
            file_id=inp.file_id,
            filename=inp.s3_key.rsplit("/", 1)[-1],
            content_type=head.get("ContentType", "application/octet-stream"),
            size_bytes=len(body),
            body_b64=base64.b64encode(body).decode("ascii"),
        )

    @activity.defn(name="detect_kind")
    def detect_kind(inp: FetchResult) -> str:
        """Return 'image' for OCR-bound files, else 'doc'."""
        return "image" if converters.is_image(inp.filename, inp.content_type) else "doc"

    @activity.defn(name="convert_doc")
    def convert_doc(inp: ConvertInput) -> ConvertResult:
        import base64
        worker_db.update_status(cfg.db_path, inp.file_id, "converting")
        data = base64.b64decode(inp.body_b64)
        text = converters.convert(inp.filename, inp.content_type, data)
        worker_db.set_extracted_text(cfg.db_path, inp.file_id, text)
        return ConvertResult(file_id=inp.file_id, text=text, chars=len(text))

    @activity.defn(name="ocr_image")
    def ocr_image(inp: ConvertInput) -> ConvertResult:
        import base64
        from PIL import Image
        import pytesseract
        import io
        worker_db.update_status(cfg.db_path, inp.file_id, "ocr")
        data = base64.b64decode(inp.body_b64)
        img = Image.open(io.BytesIO(data))
        text = pytesseract.image_to_string(img)
        worker_db.set_extracted_text(cfg.db_path, inp.file_id, text)
        return ConvertResult(file_id=inp.file_id, text=text, chars=len(text))

    @activity.defn(name="chunk_and_embed")
    def chunk_and_embed(inp: IngestInput) -> IngestResult:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        worker_db.update_status(cfg.db_path, inp.file_id, "chunking")
        text = worker_db.get_extracted_text(cfg.db_path, inp.file_id) or ""
        if not text.strip():
            worker_db.set_chunks(cfg.db_path, inp.file_id, 0)
            return IngestResult(file_id=inp.file_id, chunk_count=0)

        chunks = chunking.chunk_text(
            text, chunk_size=cfg.chunk_size, overlap=cfg.chunk_overlap,
        )

        client = chromadb.HttpClient(
            host=cfg.chroma_host, port=cfg.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        coll = client.get_or_create_collection(
            name=cfg.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

        # Wipe any prior chunks for this file (re-ingest is idempotent).
        try:
            coll.delete(where={"file_id": inp.file_id})
        except Exception:
            pass

        ids = [f"{inp.file_id}-{i:05d}" for i in range(len(chunks))]
        metas = [
            {"file_id": inp.file_id, "filename": inp.filename, "chunk": i}
            for i in range(len(chunks))
        ]

        # Add in modest batches to avoid huge requests.
        BATCH = 64
        for i in range(0, len(chunks), BATCH):
            coll.add(
                ids=ids[i:i + BATCH],
                documents=chunks[i:i + BATCH],
                metadatas=metas[i:i + BATCH],
            )

        worker_db.set_chunks(cfg.db_path, inp.file_id, len(chunks))
        return IngestResult(file_id=inp.file_id, chunk_count=len(chunks))

    @activity.defn(name="mark_status")
    def mark_status(args: dict) -> str:
        """args: {file_id, status, error?}"""
        worker_db.update_status(
            cfg.db_path, args["file_id"], args["status"],
            error=args.get("error"),
        )
        return args["status"]

    return {
        "fetch_from_s3": fetch_from_s3,
        "detect_kind": detect_kind,
        "convert_doc": convert_doc,
        "ocr_image": ocr_image,
        "chunk_and_embed": chunk_and_embed,
        "mark_status": mark_status,
    }
