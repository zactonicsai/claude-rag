"""Resilient Temporal connect for the API process."""
from __future__ import annotations
import asyncio
import logging

from temporalio.client import Client


async def connect_with_retry(
    target: str,
    namespace: str,
    *,
    attempts: int = 6,
    initial_delay: float = 0.5,
    max_delay: float = 4.0,
) -> Client:
    """Short retry loop suited to a request handler — bounded so we don't
    hold the HTTP connection open for too long if Temporal is genuinely down.
    """
    log = logging.getLogger("backend.temporal")
    delay = initial_delay
    last_err: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return await Client.connect(target, namespace=namespace)
        except Exception as e:  # noqa: BLE001
            last_err = e
            log.warning("Temporal connect attempt %d/%d: %s", i, attempts, e)
            if i == attempts:
                break
            await asyncio.sleep(delay)
            delay = min(max_delay, delay * 1.5)
    assert last_err is not None
    raise last_err
