"""Claude API client wrapper with cost computation."""
from __future__ import annotations
from dataclasses import dataclass
from anthropic import Anthropic


@dataclass
class ClaudeCallResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class ClaudeClient:
    def __init__(self, api_key: str, model: str,
                 price_in_per_mtok: float, price_out_per_mtok: float,
                 max_output_tokens: int = 1024):
        self._client = Anthropic(api_key=api_key)
        self.model = model
        self.price_in = price_in_per_mtok
        self.price_out = price_out_per_mtok
        self.max_output_tokens = max_output_tokens

    def chat(self, system: str, user_message: str) -> ClaudeCallResult:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_output_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        # Concatenate text blocks
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        text = "".join(parts)
        return ClaudeCallResult(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=self.model,
        )

    def cost_for(self, in_tok: int, out_tok: int) -> tuple[float, float, float]:
        """Return (input_cost, output_cost, total) in USD."""
        ic = (in_tok / 1_000_000.0) * self.price_in
        oc = (out_tok / 1_000_000.0) * self.price_out
        return ic, oc, ic + oc
