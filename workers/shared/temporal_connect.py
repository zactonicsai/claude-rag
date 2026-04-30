"""Resilient Temporal connect — retries on transient errors during boot.

`condition: service_healthy` in compose handles the cold-start ordering, but
this guards the case where Temporal is briefly unavailable (e.g. a restart)
while a worker is already up.
"""
from __future__ import annotations
import asyncio
import logging

from temporalio.client import Client


async def connect_with_retry(
    target: str,
    namespace: str,
    *,
    attempts: int = 60,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    logger: logging.Logger | None = None,
) -> Client:
    """Try to `Client.connect(target, namespace=...)` up to `attempts` times,
    with exponential backoff capped at `max_delay`. Re-raises the last error
    if all attempts fail.
    """
    log = logger or logging.getLogger(__name__)
    delay = initial_delay
    last_err: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            client = await Client.connect(target, namespace=namespace)
            if i > 1:
                log.info("connected to Temporal at %s after %d attempt(s)", target, i)
            return client
        except Exception as e:  # noqa: BLE001 — boot-time best-effort
            last_err = e
            log.warning(
                "Temporal connect attempt %d/%d failed (%s); retrying in %.1fs",
                i, attempts, type(e).__name__, delay,
            )
            await asyncio.sleep(delay)
            delay = min(max_delay, delay * 1.5)
    assert last_err is not None
    raise last_err
