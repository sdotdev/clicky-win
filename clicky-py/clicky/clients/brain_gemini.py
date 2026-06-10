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
            msg = (
                f"Gemini API error {exc.response.status_code} for model={model!r}. "
                "Check that the model name is valid (e.g. gemini-2.5-flash, gemini-2.0-flash) "
                f"and that your API key is correct. URL: {url}"
            )
            logger.error(msg)
            self.error.emit(msg)
            raise

        except Exception as exc:
            self.error.emit(str(exc))
            raise
