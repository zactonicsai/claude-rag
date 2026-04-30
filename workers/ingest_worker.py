"""Ingest / orchestration worker.

Hosts:
  • the FileProcessingWorkflow definition (so the workflow can run
    against the `file-processing` task queue that the API targets);
  • the lightweight activities (`fetch_from_s3`, `detect_kind`,
    `chunk_and_embed`, `mark_status`) on the `chroma-ingestion` queue.
"""
from __future__ import annotations
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.worker import Worker

from shared.activities import make_activities
from shared.workflows import FileProcessingWorkflow
from shared.config import WorkerConfig
from shared.temporal_connect import connect_with_retry

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [ingest-worker] %(message)s")


async def main() -> None:
    cfg = WorkerConfig.from_env()
    client = await connect_with_retry(cfg.temporal_host, cfg.temporal_namespace,
                                      logger=logging.getLogger("ingest-worker"))
    acts = make_activities(cfg)

    # Worker A — runs the workflow against the queue the API targets.
    workflow_worker = Worker(
        client,
        task_queue=cfg.task_queue_main,
        workflows=[FileProcessingWorkflow],
    )

    # Worker B — runs the cheap sync activities on the ingestion queue.
    with ThreadPoolExecutor(max_workers=8) as pool:
        activity_worker = Worker(
            client,
            task_queue=cfg.task_queue_ingest,
            activities=[
                acts["fetch_from_s3"],
                acts["detect_kind"],
                acts["chunk_and_embed"],
                acts["mark_status"],
            ],
            activity_executor=pool,
        )

        logging.info("ingest-worker: workflow queue=%s, activity queue=%s",
                     cfg.task_queue_main, cfg.task_queue_ingest)
        await asyncio.gather(workflow_worker.run(), activity_worker.run())


if __name__ == "__main__":
    asyncio.run(main())
