"""System tray icon for ClickyWin.

Minimal tray: static icon, context menu with Settings / Models / Show History / Quit.
The Models submenu lets the user switch Brain / Ears / Mouth providers live.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from clicky.icon_factory import icon_for_state
from clicky.state import VoiceState

logger = logging.getLogger(__name__)

_BRAIN_PROVIDERS = {
    "ollama": "Brain: Ollama (local)",
    "gemini": "Brain: Gemini (Google API)",
    "anthropic_worker": "Brain: Claude (cloud)",
}
_EARS_PROVIDERS = {
    "faster_whisper": "Ears: faster-whisper (local)",
    "assemblyai_worker": "Ears: AssemblyAI (cloud)",
}
_MOUTH_PROVIDERS = {
    "kokoro": "Mouth: Kokoro (local)",
    "elevenlabs_worker": "Mouth: ElevenLabs (cloud)",
}


class TrayIcon(QSystemTrayIcon):
    """System tray icon with Settings / Models / Show History / Quit menu."""

    show_history_requested = Signal()
    show_settings_requested = Signal()
    # Emitted when the user switches a provider via the Models menu.
    # app.py connects this to reinitialize the AI clients.
    provider_changed = Signal()
    # Viral effect triggers.
    power_mode_toggled = Signal()
    celebrate_requested = Signal()
    neon_scan_requested = Signal()

    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        self._config_path = config_path
        self.setIcon(icon_for_state(VoiceState.IDLE))
        self.setToolTip("ClickyWin")

        menu = QMenu()

        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(lambda: self.show_settings_requested.emit())
        menu.addAction(settings_action)

        # Models submenu — only shown when we have a config path to write to
        if config_path is not None:
            models_menu = self._build_models_menu(menu)
            menu.addMenu(models_menu)

        # Effects submenu — viral visual overlays.
        effects_menu = QMenu("Effects", menu)
        power_action = QAction("Toggle Power Mode  ⚡", effects_menu)
        power_action.triggered.connect(lambda: self.power_mode_toggled.emit())
        effects_menu.addAction(power_action)
        celebrate_action = QAction("Celebrate  🎆", effects_menu)
        celebrate_action.triggered.connect(lambda: self.celebrate_requested.emit())
        effects_menu.addAction(celebrate_action)
        scan_action = QAction("Neon Scan  🛰", effects_menu)
        scan_action.triggered.connect(lambda: self.neon_scan_requested.emit())
        effects_menu.addAction(scan_action)
        menu.addMenu(effects_menu)

        history_action = QAction("Show History", menu)
        history_action.triggered.connect(lambda: self.show_history_requested.emit())
        menu.addAction(history_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._on_quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def _build_models_menu(self, parent: QMenu) -> QMenu:
        """Build the Models submenu with radio buttons for each role."""
        current = self._read_current_providers()

        models_menu = QMenu("Models", parent)

        # Brain submenu
        brain_menu = QMenu("Brain", models_menu)
        brain_group = QActionGroup(brain_menu)
        brain_group.setExclusive(True)
        for key, label in _BRAIN_PROVIDERS.items():
            act = QAction(label, brain_menu)
            act.setCheckable(True)
            act.setChecked(current.get("brain") == key)
            act.triggered.connect(lambda checked, k=key: self._switch_provider("brain", k))
            brain_group.addAction(act)
            brain_menu.addAction(act)
        models_menu.addMenu(brain_menu)

        # Ears submenu
        ears_menu = QMenu("Ears", models_menu)
        ears_group = QActionGroup(ears_menu)
        ears_group.setExclusive(True)
        for key, label in _EARS_PROVIDERS.items():
            act = QAction(label, ears_menu)
            act.setCheckable(True)
            act.setChecked(current.get("ears") == key)
            act.triggered.connect(lambda checked, k=key: self._switch_provider("ears", k))
            ears_group.addAction(act)
            ears_menu.addAction(act)
        models_menu.addMenu(ears_menu)

        # Mouth submenu
        mouth_menu = QMenu("Mouth", models_menu)
        mouth_group = QActionGroup(mouth_menu)
        mouth_group.setExclusive(True)
        for key, label in _MOUTH_PROVIDERS.items():
            act = QAction(label, mouth_menu)
            act.setCheckable(True)
            act.setChecked(current.get("mouth") == key)
            act.triggered.connect(lambda checked, k=key: self._switch_provider("mouth", k))
            mouth_group.addAction(act)
            mouth_menu.addAction(act)
        models_menu.addMenu(mouth_menu)

        return models_menu

    def _read_current_providers(self) -> dict[str, str]:
        """Read current provider selections from config.toml."""
        if self._config_path is None or not self._config_path.exists():
            return {}
        try:
            data = tomllib.loads(self._config_path.read_text(encoding="utf-8"))
            return {
                "brain": (data.get("brain") or {}).get("provider", "ollama"),
                "ears": (data.get("ears") or {}).get("provider", "faster_whisper"),
                "mouth": (data.get("mouth") or {}).get("provider", "kokoro"),
            }
        except Exception:
            return {}

    def _switch_provider(self, role: str, provider: str) -> None:
        """Write the new provider to config.toml and signal app.py to reinitialize."""
        if self._config_path is None:
            return
        try:
            import tomli_w  # type: ignore[import]  # optional dep for TOML writing

            data = tomllib.loads(self._config_path.read_text(encoding="utf-8"))
            section = data.setdefault(role, {})
            section["provider"] = provider
            self._config_path.write_text(tomli_w.dumps(data), encoding="utf-8")
            logger.info("Switched %s provider to %s", role, provider)
            self.provider_changed.emit()
        except Exception as exc:
            logger.error("Failed to switch %s provider: %s", role, exc)

    def _on_quit(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()
