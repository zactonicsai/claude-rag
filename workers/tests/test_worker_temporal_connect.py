"""Tests for the worker-side Temporal retry-connect helper."""
from unittest.mock import patch, AsyncMock

import pytest

from shared.temporal_connect import connect_with_retry


@pytest.mark.asyncio
async def test_succeeds_first_try():
    fake = object()
    with patch("shared.temporal_connect.Client.connect",
               new=AsyncMock(return_value=fake)) as connect:
        out = await connect_with_retry("t:7233", "default", attempts=3,
                                       initial_delay=0.01, max_delay=0.02)
    assert out is fake
    assert connect.await_count == 1


@pytest.mark.asyncio
async def test_retries_until_success():
    fake = object()
    calls = {"n": 0}

    async def _connect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("temporal not ready")
        return fake

    with patch("shared.temporal_connect.Client.connect", new=_connect):
        out = await connect_with_retry("t:7233", "default", attempts=5,
                                       initial_delay=0.01, max_delay=0.02)
    assert out is fake
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_gives_up_after_attempts():
    with patch("shared.temporal_connect.Client.connect",
               new=AsyncMock(side_effect=RuntimeError("temporal down"))) as connect:
        with pytest.raises(RuntimeError, match="temporal down"):
            await connect_with_retry("t:7233", "default", attempts=4,
                                     initial_delay=0.01, max_delay=0.02)
    assert connect.await_count == 4
