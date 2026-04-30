"""File upload / list / view / delete routes.

Upload kicks off a Temporal workflow that runs:
    detect_type → (doc-conversion | ocr) → chunk + embed → mark ready
"""
from __future__ import annotations
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from ..config import Settings, get_settings
from ..db import FileDB
from ..models import (
    FileRecord, FileListResponse, ExtractedTextResponse,
)
from ..s3_client import make_s3_client, ensure_bucket
from ..chroma_client import (
    make_chroma_client, get_or_create_collection, delete_by_file,
)
from ..temporal_connect import connect_with_retry as temporal_connect_with_retry

router = APIRouter(prefix="/api/files", tags=["files"])


def _db(settings: Annotated[Settings, Depends(get_settings)]) -> FileDB:
    return FileDB(settings.db_path)


@router.post("/upload", status_code=202)
async def upload_file(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    db: FileDB = Depends(_db),
):
    """Stream upload to LocalStack S3, register, kick off Temporal workflow."""
    if not file.filename:
        raise HTTPException(400, "filename missing")

    file_id = uuid.uuid4().hex
    s3_key = f"uploads/{file_id}/{file.filename}"

    # ── stash bytes in S3 ────────────────────────────────────────────────
    body = await file.read()
    s3 = make_s3_client(
        settings.s3_endpoint, settings.aws_default_region,
        settings.aws_access_key_id, settings.aws_secret_access_key,
    )
    ensure_bucket(s3, settings.s3_bucket)
    s3.put_object(
        Bucket=settings.s3_bucket, Key=s3_key, Body=body,
        ContentType=file.content_type or "application/octet-stream",
    )

    # ── DB row ───────────────────────────────────────────────────────────
    now = time.time()
    workflow_id = f"file-{file_id}"
    rec = FileRecord(
        id=file_id, filename=file.filename, content_type=file.content_type,
        size_bytes=len(body), s3_key=s3_key, status="pending",
        created_at=now, updated_at=now, workflow_id=workflow_id,
    )
    db.insert(rec)

    # ── start workflow ───────────────────────────────────────────────────
    try:
        client = await temporal_connect_with_retry(
            settings.temporal_host, settings.temporal_namespace,
        )
        await client.start_workflow(
            "FileProcessingWorkflow",
            args=[{
                "file_id": file_id,
                "s3_key": s3_key,
                "filename": file.filename,
                "content_type": file.content_type or "",
            }],
            id=workflow_id,
            task_queue=settings.temporal_task_queue_main,
        )
    except Exception as e:
        db.update_status(file_id, "error", error=f"workflow start failed: {e}")
        raise HTTPException(500, f"workflow start failed: {e}")

    return {"file_id": file_id, "workflow_id": workflow_id}


@router.get("", response_model=FileListResponse)
def list_files(db: FileDB = Depends(_db)):
    return FileListResponse(files=db.list_all())


@router.get("/{file_id}", response_model=FileRecord)
def get_file(file_id: str, db: FileDB = Depends(_db)):
    rec = db.get(file_id)
    if not rec:
        raise HTTPException(404, "file not found")
    return rec


@router.get("/{file_id}/text", response_model=ExtractedTextResponse)
def get_file_text(file_id: str, db: FileDB = Depends(_db)):
    rec = db.get(file_id)
    if not rec:
        raise HTTPException(404, "file not found")
    text = db.get_text(file_id) or ""
    return ExtractedTextResponse(file_id=file_id, filename=rec.filename, text=text)


@router.delete("/{file_id}", status_code=204)
def delete_file(file_id: str,
                db: FileDB = Depends(_db),
                settings: Settings = Depends(get_settings)):
    rec = db.get(file_id)
    if not rec:
        raise HTTPException(404, "file not found")
    # Best-effort cleanup of S3 + Chroma
    try:
        s3 = make_s3_client(
            settings.s3_endpoint, settings.aws_default_region,
            settings.aws_access_key_id, settings.aws_secret_access_key,
        )
        s3.delete_object(Bucket=settings.s3_bucket, Key=rec.s3_key)
    except Exception:
        pass
    try:
        chroma = make_chroma_client(settings.chroma_host, settings.chroma_port)
        coll = get_or_create_collection(chroma, settings.chroma_collection)
        delete_by_file(coll, file_id)
    except Exception:
        pass
    db.delete(file_id)
    return JSONResponse(status_code=204, content=None)
