"""Gemini brain client using Google's OpenAI-compatible chat completions endpoint.

Google exposes an OpenAI-compatible API at:
    https://generativelanguage.googleapis.com/v1beta/openai/

This client subclasses OllamaLLMClient (which targets any OpenAI-compat endpoint)
and injects the ``Authorization: Bearer <api_key>`` header required by Google.
Message format conversion from Anthropic → OpenAI format is inherited.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from PySide6.QtCore import QObject

from clicky.clients.brain_ollama import (
    OllamaLLMClient,
    _to_openai_messages,
    parse_openai_sse_stream,
)

logger = logging.getLogger(__name__)

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

# Transient server-side status codes worth retrying
_RETRYABLE_STATUS = {429, 500, 502, 503, 529}
_MAX_RETRIES = 3
_RETRY_DELAY_S = 0.6


def _gemini_error_msg(status: int, model: str, url: str) -> str:
    if status == 404:
        return (
            f"Gemini 404 for model={model!r} — model name not recognised. "
            "Valid names: gemini-2.5-flash, gemini-2.0-flash, gemini-2.5-pro"
        )
    if status == 401:
        return f"Gemini 401 — API key rejected. Check GOOGLE_API_KEY / GEMINI_API_KEY. URL: {url}"
    if status == 429:
        return f"Gemini 429 — rate limited. Retries exhausted. URL: {url}"
    if status in (500, 502, 503, 529):
        return f"Gemini {status} — server error (transient). Retries exhausted. URL: {url}"
    return f"Gemini HTTP {status} for model={model!r}. URL: {url}"


class GeminiLLMClient(OllamaLLMClient):
    """Streaming brain client for Google Gemini via the OpenAI-compatible API.

    Drop-in replacement for ``LLMClient`` — same Qt signals, same ``send()``
    signature.  Requires a Google AI API key passed at construction.

    Recommended models:
        ``gemini-2.0-flash``   — fast, multimodal, free tier available
        ``gemini-2.5-pro``     — highest quality, vision capable
        ``gemini-2.5-flash``   — balanced speed/quality, vision capable

    Signals:
        delta(str): Emitted for each text fragment as it streams in.
        done(str):  Emitted once with the full accumulated response text.
        error(str): Emitted when any exception occurs during the request.
    """

    def __init__(self, api_key: str, *, parent: QObject | None = None) -> None:
        super().__init__(_GEMINI_BASE_URL, parent=parent)
        self._api_key = api_key

    async def send(
        self,
        messages: list[dict],
        system: str,
        model: str,
        max_tokens: int = 1024,
    ) -> str:
        """POST a streaming Gemini chat completion and return the full response text."""
        url = f"{self._base_url}/chat/completions"
        openai_messages = _to_openai_messages(messages, system)
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "stream": True,
            "messages": openai_messages,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            full_text = ""
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    async with client.stream("POST", url, json=body, headers=headers) as response:
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
                logger.debug("GeminiLLMClient.send() cancelled")
                raise

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                last_exc = exc
                if status in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                    logger.warning(
                        "Gemini %d (attempt %d/%d) — retrying in %.1fs",
                        status, attempt, _MAX_RETRIES, _RETRY_DELAY_S * attempt,
                    )
                    await asyncio.sleep(_RETRY_DELAY_S * attempt)
                    continue
                msg = _gemini_error_msg(status, model, url)
                logger.error(msg)
                self.error.emit(msg)
                raise

            except Exception as exc:
                self.error.emit(str(exc))
                raise

        # Exhausted retries (should not reach here — loop raises on last attempt)
        self.error.emit(str(last_exc))
        raise last_exc  # type: ignore[misc]
