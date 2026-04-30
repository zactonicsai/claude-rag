"""FileProcessingWorkflow.

    fetch_from_s3   (any worker)
        ↓
    detect_kind     (any worker)
        ↓
    convert_doc    OR    ocr_image       ← routed by task queue
        ↓
    chunk_and_embed (ingest worker)
        ↓
    mark_status     (any worker)

Each activity is dispatched to the queue most appropriate for the worker that
owns the dependencies it needs.
"""
from __future__ import annotations
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    # These imports are dataclass-only; safe to pass through to activities.
    from .activities import (
        FetchInput, FetchResult, ConvertInput, ConvertResult,
        IngestInput, IngestResult,
    )


@workflow.defn(name="FileProcessingWorkflow")
class FileProcessingWorkflow:

    @workflow.run
    async def run(self, params: dict) -> dict:
        file_id = params["file_id"]
        s3_key = params["s3_key"]

        # Task queue names — workflow worker is started with a config that
        # provides these via a Temporal "search attributes"-equivalent. We
        # keep them as constants matching docker-compose env defaults.
        TQ_DOC = "doc-conversion"
        TQ_OCR = "ocr-processing"
        TQ_INGEST = "chroma-ingestion"

        try:
            # 1. Fetch from S3 — any worker can do this; route to ingest queue
            #    since it's lightweight.
            fetched: FetchResult = await workflow.execute_activity(
                "fetch_from_s3",
                FetchInput(file_id=file_id, s3_key=s3_key),
                task_queue=TQ_INGEST,
                start_to_close_timeout=timedelta(minutes=2),
                result_type=FetchResult,
            )

            # 2. Decide doc vs image (also lightweight)
            kind: str = await workflow.execute_activity(
                "detect_kind", fetched,
                task_queue=TQ_INGEST,
                start_to_close_timeout=timedelta(seconds=30),
                result_type=str,
            )

            # 3. Convert to text
            convert_input = ConvertInput(
                file_id=fetched.file_id,
                filename=fetched.filename,
                content_type=fetched.content_type,
                body_b64=fetched.body_b64,
            )
            if kind == "image":
                converted: ConvertResult = await workflow.execute_activity(
                    "ocr_image", convert_input,
                    task_queue=TQ_OCR,
                    start_to_close_timeout=timedelta(minutes=10),
                    result_type=ConvertResult,
                )
            else:
                converted = await workflow.execute_activity(
                    "convert_doc", convert_input,
                    task_queue=TQ_DOC,
                    start_to_close_timeout=timedelta(minutes=5),
                    result_type=ConvertResult,
                )

            # 4. Chunk + embed in ChromaDB
            ingested: IngestResult = await workflow.execute_activity(
                "chunk_and_embed",
                IngestInput(file_id=file_id, filename=fetched.filename),
                task_queue=TQ_INGEST,
                start_to_close_timeout=timedelta(minutes=10),
                result_type=IngestResult,
            )

            # 5. Mark ready
            await workflow.execute_activity(
                "mark_status",
                {"file_id": file_id, "status": "ready"},
                task_queue=TQ_INGEST,
                start_to_close_timeout=timedelta(seconds=15),
                result_type=str,
            )
            return {
                "file_id": file_id,
                "kind": kind,
                "chars": converted.chars,
                "chunks": ingested.chunk_count,
                "status": "ready",
            }

        except Exception as e:  # noqa: BLE001 — workflow surface-level error
            # Best-effort: mark file as errored so the UI shows it.
            try:
                await workflow.execute_activity(
                    "mark_status",
                    {"file_id": file_id, "status": "error", "error": str(e)[:500]},
                    task_queue=TQ_INGEST,
                    start_to_close_timeout=timedelta(seconds=15),
                    result_type=str,
                )
            except Exception:
                pass
            raise
