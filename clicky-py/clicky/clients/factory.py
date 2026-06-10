"""Client factory: instantiate the right AI client for each role from config.

Each ``create_*`` function reads the provider field from the matching config
section and returns the appropriate concrete client.  Adding a new provider
means adding one branch here and one new client module — nothing else changes.
"""

from __future__ import annotations

from PySide6.QtCore import QObject

from clicky.config import Config, ConfigError


def create_brain(cfg: Config, parent: QObject | None = None):
    """Return the configured brain (LLM) client."""
    provider = cfg.brain.provider

    if provider == "ollama":
        from clicky.clients.brain_ollama import OllamaLLMClient

        return OllamaLLMClient(cfg.brain.base_url, parent=parent)

    if provider == "gemini":
        from clicky.clients.brain_gemini import GeminiLLMClient

        return GeminiLLMClient(cfg.brain.api_key, parent=parent)

    if provider == "anthropic_worker":
        from clicky.clients.llm_client import LLMClient

        _require_worker_url(cfg, "brain")
        return LLMClient(cfg.worker_url, parent=parent)  # type: ignore[arg-type]

    raise ConfigError(f"Unknown brain provider: {provider!r}")


def create_ears(cfg: Config, parent: QObject | None = None):
    """Return the configured ears (STT) client."""
    provider = cfg.ears.provider

    if provider == "faster_whisper":
        from clicky.clients.ears_faster_whisper import FasterWhisperClient

        return FasterWhisperClient(
            model_name=cfg.ears.model,
            device=cfg.ears.device,
            compute_type=cfg.ears.compute_type,
            parent=parent,
        )

    if provider == "assemblyai_worker":
        from clicky.clients.transcription_client import TranscriptionClient

        _require_worker_url(cfg, "ears")
        return TranscriptionClient(cfg.worker_url, parent=parent)  # type: ignore[arg-type]

    raise ConfigError(f"Unknown ears provider: {provider!r}")


def create_mouth(cfg: Config, parent: QObject | None = None):
    """Return the configured mouth (TTS) client."""
    provider = cfg.mouth.provider

    if provider == "kokoro":
        from clicky.clients.mouth_kokoro import KokoroTTSClient

        return KokoroTTSClient(cfg.mouth.voice, parent=parent)

    if provider == "elevenlabs_worker":
        from clicky.clients.tts_client import TTSClient

        _require_worker_url(cfg, "mouth")
        return TTSClient(cfg.worker_url, parent=parent)  # type: ignore[arg-type]

    raise ConfigError(f"Unknown mouth provider: {provider!r}")


def _require_worker_url(cfg: Config, role: str) -> None:
    if not cfg.worker_url:
        raise ConfigError(
            f"{role} provider requires worker_url to be set in config.toml"
        )
