"""Thin wrapper around the Claude API.

The rest of the app only sees `LLMClient.complete(system, user, schema) -> str`, so tests
can pass a fake client and never touch the network.

The model name comes from the env var CLAUDE_MODEL and the key from ANTHROPIC_API_KEY,
both read from `.env` (CLAUDE.md section 4). Nothing is hard-coded.
"""
from __future__ import annotations

import os
from typing import Any, Optional, Protocol

MAX_TOKENS = 4000  # one short paragraph per test row; a CBC has about 25 rows


class LLMError(Exception):
    """The call did not produce usable text. The reason never contains report values."""


class LLMClient(Protocol):
    def complete(self, system: str, user: str, schema: dict) -> str: ...


class ClaudeClient:
    def __init__(self, model: Optional[str] = None, sdk: Any = None):
        self.model = model or os.environ.get("CLAUDE_MODEL", "")
        if not self.model:
            raise LLMError("CLAUDE_MODEL is not set (add it to .env)")
        if sdk is None:
            import anthropic  # imported here so tests and the extractor never need it

            sdk = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.sdk = sdk

    def complete(self, system: str, user: str, schema: dict) -> str:
        import anthropic

        try:
            response = self.sdk.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
                # Asks the API to return JSON in this shape. The verifier still checks
                # everything; this only makes malformed answers rarer.
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.APIError as exc:
            # Only the class name: the message can echo parts of the request.
            raise LLMError(f"api_error:{type(exc).__name__}") from None
        if response.stop_reason != "end_turn":
            # "refusal" or "max_tokens": either way the text is missing or cut off.
            raise LLMError(f"stop_reason:{response.stop_reason}")
        text = "".join(b.text for b in response.content if b.type == "text")
        if not text.strip():
            raise LLMError("empty_response")
        return text


def default_client() -> ClaudeClient:
    """Client built from `.env`. Raises LLMError when it is not configured."""
    from dotenv import load_dotenv

    load_dotenv()  # does not override variables that are already set
    return ClaudeClient()
