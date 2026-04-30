"""OCR worker — owns image-to-text via tesseract."""
from __future__ import annotations
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.worker import Worker

from shared.activities import make_activities
from shared.config import WorkerConfig
from shared.temporal_connect import connect_with_retry

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [ocr-worker] %(message)s")


async def main() -> None:
    cfg = WorkerConfig.from_env()
    client = await connect_with_retry(cfg.temporal_host, cfg.temporal_namespace,
                                      logger=logging.getLogger("ocr-worker"))
    acts = make_activities(cfg)

    with ThreadPoolExecutor(max_workers=4) as pool:
        worker = Worker(
            client,
            task_queue=cfg.task_queue_ocr,
            activities=[acts["ocr_image"]],
            activity_executor=pool,
        )
        logging.info("ocr-worker listening on %s", cfg.task_queue_ocr)
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
