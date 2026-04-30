"""Tests for the Claude client (just the cost math — no live API calls)."""
from app.claude_client import ClaudeClient


def test_cost_for_zero_tokens():
    c = ClaudeClient(api_key="x", model="m",
                     price_in_per_mtok=3.0, price_out_per_mtok=15.0)
    ic, oc, tot = c.cost_for(0, 0)
    assert (ic, oc, tot) == (0.0, 0.0, 0.0)


def test_cost_basic():
    c = ClaudeClient(api_key="x", model="m",
                     price_in_per_mtok=3.0, price_out_per_mtok=15.0)
    ic, oc, tot = c.cost_for(1_000_000, 1_000_000)
    assert ic == 3.0
    assert oc == 15.0
    assert tot == 18.0


def test_cost_partial():
    c = ClaudeClient(api_key="x", model="m",
                     price_in_per_mtok=2.0, price_out_per_mtok=10.0)
    ic, oc, tot = c.cost_for(500_000, 100_000)
    assert ic == 1.0
    assert oc == 1.0
    assert tot == 2.0
