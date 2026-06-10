"""Config loader for ClickyWin.

Reads config.toml from the OS-appropriate per-user config directory via
platformdirs. Supports per-role provider sections ([brain], [ears], [mouth])
with backward compatibility for the old flat format (worker_url + default_model).
"""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PLACEHOLDER_WORKER_URL = "https://clicky-win-proxy.your-subdomain.workers.dev"

ALLOWED_HOTKEYS = {"ctrl+alt", "right_ctrl"}
ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}

ALLOWED_BRAIN_PROVIDERS = {"ollama", "gemini", "anthropic_worker"}
ALLOWED_EARS_PROVIDERS = {"faster_whisper", "assemblyai_worker"}
ALLOWED_MOUTH_PROVIDERS = {"kokoro", "elevenlabs_worker"}


class ConfigError(Exception):
    """Raised when the config file cannot be loaded or fails validation."""


@dataclass(frozen=True)
class BrainConfig:
    provider: str = "ollama"
    model: str = "qwen2.5vl:7b"
    base_url: str = "http://localhost:11434/v1"
    # Required when provider == "gemini"; read from config or GOOGLE_API_KEY env var
    api_key: str = ""


@dataclass(frozen=True)
class EarsConfig:
    provider: str = "faster_whisper"
    model: str = "distil-large-v3"
    device: str = "cuda"
    compute_type: str = "float16"


@dataclass(frozen=True)
class MouthConfig:
    provider: str = "kokoro"
    voice: str = "af_heart"


@dataclass(frozen=True)
class Config:
    hotkey: str
    log_level: str
    lerp_factor: float
    knowledge_dir: Path | None
    brain: BrainConfig
    ears: EarsConfig
    mouth: MouthConfig
    tts_enabled: bool = field(default=True)
    shake_sensitivity: float = field(default=0.5)
    # Only populated when a *_worker provider is configured
    worker_url: str | None = field(default=None)

    @classmethod
    def from_path(cls, path: Path) -> Config:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ConfigError(f"cannot read config file at {path}: {exc}") from exc
        try:
            data = tomllib.loads(raw.decode("utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            raise ConfigError(f"cannot parse TOML at {path}: {exc}") from exc

        hotkey = data.get("hotkey", "ctrl+alt")
        if hotkey not in ALLOWED_HOTKEYS:
            raise ConfigError(
                f"hotkey must be one of {sorted(ALLOWED_HOTKEYS)}, got {hotkey!r}"
            )

        log_level = data.get("log_level", "INFO")
        if log_level not in ALLOWED_LOG_LEVELS:
            raise ConfigError(
                f"log_level must be one of {sorted(ALLOWED_LOG_LEVELS)}, got {log_level!r}"
            )

        lerp_factor_raw = data.get("lerp_factor", 0.15)
        lerp_factor = float(max(0.01, min(1.0, lerp_factor_raw)))

        knowledge_dir_raw = data.get("knowledge_dir")
        if isinstance(knowledge_dir_raw, str) and knowledge_dir_raw.strip():
            knowledge_dir = Path(knowledge_dir_raw)
        else:
            knowledge_dir = path.parent / "knowledge"
        if not knowledge_dir.is_dir():
            knowledge_dir = None

        # --- Per-role provider sections ---

        brain = _parse_brain(data)
        ears = _parse_ears(data)
        mouth = _parse_mouth(data)

        # worker_url: required only when a *_worker provider is active
        needs_worker = (
            brain.provider == "anthropic_worker"
            or ears.provider == "assemblyai_worker"
            or mouth.provider == "elevenlabs_worker"
        )

        worker_url: str | None = None
        if needs_worker:
            raw_url = data.get("worker_url")
            if not isinstance(raw_url, str) or not raw_url:
                raise ConfigError(
                    "worker_url is required when using anthropic_worker, "
                    "assemblyai_worker, or elevenlabs_worker providers"
                )
            if raw_url == PLACEHOLDER_WORKER_URL:
                raise ConfigError(
                    f"worker_url is still the placeholder value. Edit {path} and set it "
                    "to your deployed Cloudflare Worker URL."
                )
            worker_url = raw_url

        tts_enabled = bool(data.get("tts_enabled", True))

        shake_sensitivity = float(max(0.0, min(1.0, data.get("shake_sensitivity", 0.5))))

        return cls(
            hotkey=hotkey,
            log_level=log_level,
            lerp_factor=lerp_factor,
            knowledge_dir=knowledge_dir,
            brain=brain,
            ears=ears,
            mouth=mouth,
            tts_enabled=tts_enabled,
            shake_sensitivity=shake_sensitivity,
            worker_url=worker_url,
        )

    @property
    def default_model(self) -> str:
        """Backward-compat shim: returns the active brain model identifier."""
        return self.brain.model

    @staticmethod
    def ensure_exists(target_path: Path, example_path: Path) -> bool:
        """Copy example to target if target does not exist. Returns True if created."""
        if target_path.exists():
            return False
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(example_path, target_path)
        return True


_BRAIN_DEFAULTS: dict[str, dict[str, str]] = {
    "ollama":           {"model": "qwen2.5vl:7b",     "base_url": "http://localhost:11434/v1"},
    "gemini":           {"model": "gemini-2.5-flash",  "base_url": ""},
    "anthropic_worker": {"model": "claude-sonnet-4-6", "base_url": ""},
}


def _parse_brain(data: dict) -> BrainConfig:
    section = data.get("brain")
    if section is None:
        # Backward compat: flat default_model → anthropic_worker
        old_model = data.get("default_model", "claude-sonnet-4-6")
        return BrainConfig(provider="anthropic_worker", model=old_model, base_url="")
    if not isinstance(section, dict):
        raise ConfigError("[brain] must be a TOML table")
    provider = section.get("provider", "ollama")
    if provider not in ALLOWED_BRAIN_PROVIDERS:
        raise ConfigError(
            f"brain.provider must be one of {sorted(ALLOWED_BRAIN_PROVIDERS)}, got {provider!r}"
        )
    defaults = _BRAIN_DEFAULTS[provider]
    api_key = (
        section.get("api_key", "")
        or os.environ.get("GOOGLE_API_KEY", "")
        or os.environ.get("GEMINI_API_KEY", "")
    )
    if provider == "gemini" and not api_key:
        raise ConfigError(
            "brain.api_key is required for the gemini provider "
            "(or set GOOGLE_API_KEY or GEMINI_API_KEY environment variable)"
        )
    return BrainConfig(
        provider=provider,
        model=section.get("model") or defaults["model"],
        base_url=section.get("base_url") or defaults["base_url"],
        api_key=api_key,
    )


def _parse_ears(data: dict) -> EarsConfig:
    section = data.get("ears")
    if section is None:
        # Backward compat: no ears section → assemblyai_worker
        return EarsConfig(provider="assemblyai_worker")
    if not isinstance(section, dict):
        raise ConfigError("[ears] must be a TOML table")
    provider = section.get("provider", "faster_whisper")
    if provider not in ALLOWED_EARS_PROVIDERS:
        raise ConfigError(
            f"ears.provider must be one of {sorted(ALLOWED_EARS_PROVIDERS)}, got {provider!r}"
        )
    return EarsConfig(
        provider=provider,
        model=section.get("model", "distil-large-v3"),
        device=section.get("device", "cuda"),
        compute_type=section.get("compute_type", "float16"),
    )


def _parse_mouth(data: dict) -> MouthConfig:
    section = data.get("mouth")
    if section is None:
        # Backward compat: no mouth section → elevenlabs_worker
        return MouthConfig(provider="elevenlabs_worker")
    if not isinstance(section, dict):
        raise ConfigError("[mouth] must be a TOML table")
    provider = section.get("provider", "kokoro")
    if provider not in ALLOWED_MOUTH_PROVIDERS:
        raise ConfigError(
            f"mouth.provider must be one of {sorted(ALLOWED_MOUTH_PROVIDERS)}, got {provider!r}"
        )
    return MouthConfig(
        provider=provider,
        voice=section.get("voice", "af_heart"),
    )
