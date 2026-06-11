"""Tests for the [effects] config section."""

from pathlib import Path

from clicky.config import Config

# All-local providers so worker_url is never required by these tests.
_LOCAL = (
    "hotkey = 'ctrl+alt'\n"
    "[brain]\nprovider = 'ollama'\n"
    "[ears]\nprovider = 'faster_whisper'\n"
    "[mouth]\nprovider = 'kokoro'\n"
)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_effects_defaults_when_section_absent(tmp_path):
    cfg = Config.from_path(_write(tmp_path, _LOCAL))
    assert cfg.power_mode_enabled is False
    assert cfg.neon_scan_demo is True
    assert cfg.celebrate_on_success is False


def test_effects_values_parsed(tmp_path):
    body = _LOCAL + (
        "[effects]\n"
        "power_mode_enabled = true\n"
        "neon_scan_demo = false\n"
        "celebrate_on_success = true\n"
    )
    cfg = Config.from_path(_write(tmp_path, body))
    assert cfg.power_mode_enabled is True
    assert cfg.neon_scan_demo is False
    assert cfg.celebrate_on_success is True


def test_effects_section_not_a_table_falls_back_to_defaults(tmp_path):
    cfg = Config.from_path(_write(tmp_path, _LOCAL + "effects = 5\n"))
    assert cfg.power_mode_enabled is False
    assert cfg.neon_scan_demo is True
