"""Ollama brain client using the OpenAI-compatible chat completions API.

Provides the same Qt signals and ``send()`` interface as ``LLMClient`` but
targets a local Ollama instance (or any OpenAI-compatible endpoint) instead of
the Anthropic Messages API.  Message conversion from Anthropic format to OpenAI
format happens internally so ``CompanionManager`` needs no changes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Iterator

import httpx
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


def _anthropic_to_openai_content(content: list[dict]) -> list[dict]:
    """Convert an Anthropic content block list to OpenAI format.

    Anthropic image blocks use ``{"type": "image", "source": {"type": "base64",
    "media_type": "...", "data": "..."}}``.  OpenAI (and Ollama) expect
    ``{"type": "image_url", "image_url": {"url": "data:<media_type>;base64,<data>"}}``.
    Text blocks are identical in both formats.
    """
    out: list[dict] = []
    for block in content:
        if block.get("type") == "image":
            src = block.get("source", {})
            media_type = src.get("media_type", "image/jpeg")
            data = src.get("data", "")
            out.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{data}"},
                }
            )
        else:
            out.append(block)
    return out


def _to_openai_messages(anthropic_messages: list[dict], system: str) -> list[dict]:
    """Convert Anthropic Messages API ``messages`` array to OpenAI format.

    Prepends the system prompt as a ``role: system`` message (OpenAI convention).
    Converts image blocks in each user/assistant turn.
    """
    result: list[dict] = [{"role": "system", "content": system}]
    for msg in anthropic_messages:
        role = msg.get("role", "user")
        raw_content = msg.get("content", "")
        if isinstance(raw_content, str):
            result.append({"role": role, "content": raw_content})
        elif isinstance(raw_content, list):
            result.append({"role": role, "content": _anthropic_to_openai_content(raw_content)})
        else:
            result.append({"role": role, "content": str(raw_content)})
    return result


def parse_openai_sse_stream(raw: bytes) -> Iterator[str]:
    """Parse an OpenAI-compatible SSE byte stream and yield text delta strings.

    Each SSE event is ``data: <json>\\n\\n``.  We extract
    ``choices[0].delta.content`` from each non-``[DONE]`` event.
    """
    if not raw:
        return

    text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload_str = line[len("data:"):].strip()
        if payload_str == "[DONE]":
            continue
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            continue
        choices = payload.get("choices")
        if not choices:
            continue
        delta = choices[0].get("delta", {})
        content = delta.get("content")
        if content:
            yield content


class OllamaLLMClient(QObject):
    """Streaming brain client for any OpenAI-compatible endpoint (Ollama, etc.).

    Drop-in replacement for ``LLMClient`` — same Qt signals, same ``send()``
    signature.  Messages are converted from Anthropic format to OpenAI format
    internally.

    Signals:
        delta(str): Emitted for each text fragment as it streams in.
        done(str):  Emitted once with the full accumulated response text.
        error(str): Emitted when any exception occurs during the request.
    """

    delta = Signal(str)
    done = Signal(str)
    error = Signal(str)

    def __init__(self, base_url: str, *, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._base_url = base_url.rstrip("/")

    async def send(
        self,
        messages: list[dict],
        system: str,
        model: str,
        max_tokens: int = 1024,
    ) -> str:
        """POST a streaming chat completion and return the full response text.

        Args:
            messages:   Anthropic-format messages array (converted internally).
            system:     System prompt string.
            model:      Model identifier (e.g. ``"qwen2.5vl:7b"``).
            max_tokens: Maximum tokens to generate.

        Returns:
            The fully accumulated response text.
        """
        url = f"{self._base_url}/chat/completions"
        openai_messages = _to_openai_messages(messages, system)
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "stream": True,
            "messages": openai_messages,
        }

        full_text = ""

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=body) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        for fragment in parse_openai_sse_stream(line.encode()):
                            self.delta.emit(fragment)
                            full_text += fragment

            self.done.emit(full_text)
            return full_text

        except asyncio.CancelledError:
            logger.debug("OllamaLLMClient.send() cancelled")
            raise

        except Exception as exc:
            self.error.emit(str(exc))
            raise
