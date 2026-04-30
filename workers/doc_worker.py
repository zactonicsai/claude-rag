"""Doc-conversion worker.

Hosts only the activities that need pypdf/python-docx/bs4 and listens on
the `doc-conversion` task queue.
"""
from __future__ import annotations
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.worker import Worker

from shared.activities import make_activities
from shared.config import WorkerConfig
from shared.temporal_connect import connect_with_retry

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [doc-worker] %(message)s")


async def main() -> None:
    cfg = WorkerConfig.from_env()
    client = await connect_with_retry(cfg.temporal_host, cfg.temporal_namespace,
                                      logger=logging.getLogger("doc-worker"))
    acts = make_activities(cfg)

    with ThreadPoolExecutor(max_workers=8) as pool:
        worker = Worker(
            client,
            task_queue=cfg.task_queue_doc,
            activities=[acts["convert_doc"]],
            activity_executor=pool,
        )
        logging.info("doc-worker listening on %s", cfg.task_queue_doc)
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
