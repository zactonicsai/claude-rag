"""Tests for the backend's Temporal retry-connect helper."""
from unittest.mock import patch, AsyncMock

import pytest

from app.temporal_connect import connect_with_retry


@pytest.mark.asyncio
async def test_succeeds_on_first_try():
    fake = object()
    with patch("app.temporal_connect.Client.connect",
               new=AsyncMock(return_value=fake)) as connect:
        out = await connect_with_retry("t:7233", "default", attempts=3,
                                       initial_delay=0.01, max_delay=0.02)
    assert out is fake
    assert connect.await_count == 1


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    fake = object()
    side = [RuntimeError("nope"), RuntimeError("still"), fake]
    async def _connect(*a, **kw):
        v = side.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    with patch("app.temporal_connect.Client.connect", new=_connect):
        out = await connect_with_retry("t:7233", "default", attempts=5,
                                       initial_delay=0.01, max_delay=0.02)
    assert out is fake
    assert side == []  # all consumed


@pytest.mark.asyncio
async def test_gives_up_after_attempts():
    with patch("app.temporal_connect.Client.connect",
               new=AsyncMock(side_effect=RuntimeError("temporal down"))) as connect:
        with pytest.raises(RuntimeError, match="temporal down"):
            await connect_with_retry("t:7233", "default", attempts=3,
                                     initial_delay=0.01, max_delay=0.02)
    assert connect.await_count == 3
