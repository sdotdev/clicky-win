from pathlib import Path

import pytest

from clicky.config import PLACEHOLDER_WORKER_URL, Config, ConfigError


# ---------------------------------------------------------------------------
# Backward-compat: old flat format (no [brain]/[ears]/[mouth] sections)
# ---------------------------------------------------------------------------

def test_load_flat_format_with_worker_providers(tmp_path: Path) -> None:
    """Old flat config (no role sections) falls back to all *_worker providers."""
    toml_text = """
    worker_url = "https://my-worker.example.workers.dev"
    hotkey = "ctrl+alt"
    default_model = "claude-sonnet-4-6"
    log_level = "INFO"
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml_text)
    cfg = Config.from_path(config_path)
    assert cfg.worker_url == "https://my-worker.example.workers.dev"
    assert cfg.hotkey == "ctrl+alt"
    assert cfg.log_level == "INFO"
    # Backward compat: default_model property mirrors brain.model
    assert cfg.default_model == "claude-sonnet-4-6"
    assert cfg.brain.provider == "anthropic_worker"
    assert cfg.ears.provider == "assemblyai_worker"
    assert cfg.mouth.provider == "elevenlabs_worker"


def test_load_rejects_placeholder_worker_url(tmp_path: Path) -> None:
    toml_text = f"""
    worker_url = "{PLACEHOLDER_WORKER_URL}"
    hotkey = "ctrl+alt"
    log_level = "INFO"
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml_text)
    with pytest.raises(ConfigError, match="worker_url"):
        Config.from_path(config_path)


def test_load_rejects_missing_worker_url_when_required(tmp_path: Path) -> None:
    """Old flat format (no sections) requires worker_url since it implies *_worker providers."""
    config_path = tmp_path / "config.toml"
    config_path.write_text('hotkey = "ctrl+alt"\n')
    with pytest.raises(ConfigError, match="worker_url"):
        Config.from_path(config_path)


def test_load_rejects_invalid_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("this is not valid toml {{{")
    with pytest.raises(ConfigError, match="parse"):
        Config.from_path(config_path)


def test_load_rejects_invalid_hotkey(tmp_path: Path) -> None:
    toml_text = """
    hotkey = "banana"
    log_level = "INFO"

    [brain]
    provider = "ollama"
    model = "qwen2.5vl:7b"
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml_text)
    with pytest.raises(ConfigError, match="hotkey"):
        Config.from_path(config_path)


# ---------------------------------------------------------------------------
# New per-role sections
# ---------------------------------------------------------------------------

def test_load_all_local_providers(tmp_path: Path) -> None:
    toml_text = """
    hotkey = "ctrl+alt"
    log_level = "INFO"

    [brain]
    provider = "ollama"
    model = "qwen2.5vl:7b"
    base_url = "http://localhost:11434/v1"

    [ears]
    provider = "faster_whisper"
    model = "distil-large-v3"
    device = "cuda"
    compute_type = "float16"

    [mouth]
    provider = "kokoro"
    voice = "af_heart"
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml_text)
    cfg = Config.from_path(config_path)
    assert cfg.worker_url is None
    assert cfg.brain.provider == "ollama"
    assert cfg.brain.model == "qwen2.5vl:7b"
    assert cfg.ears.provider == "faster_whisper"
    assert cfg.ears.device == "cuda"
    assert cfg.mouth.provider == "kokoro"
    assert cfg.mouth.voice == "af_heart"


def test_load_mixed_providers_requires_worker_url(tmp_path: Path) -> None:
    """Using anthropic_worker for brain requires worker_url."""
    toml_text = """
    hotkey = "ctrl+alt"
    log_level = "INFO"

    [brain]
    provider = "anthropic_worker"
    model = "claude-sonnet-4-6"

    [ears]
    provider = "faster_whisper"

    [mouth]
    provider = "kokoro"
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml_text)
    with pytest.raises(ConfigError, match="worker_url"):
        Config.from_path(config_path)


def test_load_mixed_providers_with_worker_url(tmp_path: Path) -> None:
    toml_text = """
    worker_url = "https://my-worker.example.workers.dev"
    hotkey = "ctrl+alt"
    log_level = "INFO"

    [brain]
    provider = "anthropic_worker"
    model = "claude-sonnet-4-6"

    [ears]
    provider = "faster_whisper"

    [mouth]
    provider = "kokoro"
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml_text)
    cfg = Config.from_path(config_path)
    assert cfg.worker_url == "https://my-worker.example.workers.dev"
    assert cfg.brain.provider == "anthropic_worker"
    assert cfg.ears.provider == "faster_whisper"
    assert cfg.mouth.provider == "kokoro"


def test_load_rejects_unknown_brain_provider(tmp_path: Path) -> None:
    toml_text = """
    hotkey = "ctrl+alt"
    log_level = "INFO"

    [brain]
    provider = "gpt4all"
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml_text)
    with pytest.raises(ConfigError, match="brain.provider"):
        Config.from_path(config_path)


def test_default_model_property_mirrors_brain_model(tmp_path: Path) -> None:
    """default_model shim used by CompanionManager returns brain.model."""
    toml_text = """
    hotkey = "ctrl+alt"
    log_level = "INFO"

    [brain]
    provider = "ollama"
    model = "llama3.2-vision"
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml_text)
    cfg = Config.from_path(config_path)
    assert cfg.default_model == "llama3.2-vision"
    assert cfg.default_model == cfg.brain.model


# ---------------------------------------------------------------------------
# ensure_exists
# ---------------------------------------------------------------------------

def test_ensure_exists_creates_from_example(tmp_path: Path) -> None:
    example_path = tmp_path / "config.example.toml"
    example_path.write_text('hotkey = "ctrl+alt"\n')
    target_path = tmp_path / "nested" / "config.toml"
    Config.ensure_exists(target_path, example_path)
    assert target_path.exists()
    assert target_path.read_text() == example_path.read_text()


def test_ensure_exists_noop_when_already_present(tmp_path: Path) -> None:
    example_path = tmp_path / "config.example.toml"
    example_path.write_text('hotkey = "ctrl+alt"\n')
    target_path = tmp_path / "config.toml"
    target_path.write_text('[brain]\nprovider = "ollama"\n')
    Config.ensure_exists(target_path, example_path)
    assert "[brain]" in target_path.read_text()
