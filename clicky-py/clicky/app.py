"""ClickyWin QApplication bootstrap.

Resolves the config file path via platformdirs, ensures the file exists
(creating from config.example.toml on first run), loads it, and holds
the resulting Config for downstream components to read.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass
from pathlib import Path

import qasync
from platformdirs import user_config_dir, user_log_dir
from PySide6.QtWidgets import QApplication

from clicky.clients.llm_client import LLMClient
from clicky.clients.transcription_client import TranscriptionClient
from clicky.clients.tts_client import TTSClient
from clicky.companion_manager import CompanionManager
from clicky.config import Config, ConfigError
from clicky.hotkey import HotkeyMonitor
from clicky.logging_config import configure_logging
from clicky.mic_capture import MicCapture
from clicky.output_capture import OutputCapture
from clicky.screen_capture import capture_all
from clicky.state import VoiceState
from clicky.ui.companion_widget import CompanionWidget
from clicky.ui.history_window import HistoryWindow
from clicky.ui.settings_window import QtLogHandler, SettingsWindow
from clicky.ui.text_input_widget import TextInputWidget
from clicky.ui.tray_icon import TrayIcon

APP_NAME = "ClickyWin"
APP_AUTHOR = "ClickyWin"

logger = logging.getLogger(__name__)


@dataclass
class BootstrapResult:
    app: QApplication
    config: Config | None
    config_error: ConfigError | None
    was_first_run: bool
    config_path: Path
    log_dir: Path


def _example_config_path() -> Path:
    # config.example.toml sits next to the clicky package directory
    # (i.e. inside clicky-py/, alongside clicky/).
    return Path(__file__).resolve().parent.parent / "config.example.toml"


def bootstrap(argv: list[str] | None = None) -> BootstrapResult:
    # Qt 6 sets PROCESS_PER_MONITOR_DPI_AWARE_V2 internally during
    # QApplication init — calling SetProcessDpiAwareness ourselves is
    # redundant and raises "Access is denied" if Qt gets there first.
    # mss captures at raw physical pixels regardless, so no explicit call
    # is needed.

    argv = argv if argv is not None else sys.argv
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_AUTHOR)
    app.setQuitOnLastWindowClosed(False)  # tray app — closing panel must not quit

    config_dir = Path(user_config_dir(APP_NAME, appauthor=False, roaming=True))
    config_path = config_dir / "config.toml"
    log_dir = Path(user_log_dir(APP_NAME, appauthor=False))

    was_first_run = Config.ensure_exists(config_path, _example_config_path())

    try:
        config = Config.from_path(config_path)
        config_error = None
    except ConfigError as exc:
        config = None
        config_error = exc

    return BootstrapResult(
        app=app,
        config=config,
        config_error=config_error,
        was_first_run=was_first_run,
        config_path=config_path,
        log_dir=log_dir,
    )


def run() -> int:
    """Start the ClickyWin tray app and run the Qt event loop."""
    result = bootstrap()

    log_level = result.config.log_level if result.config else "INFO"
    configure_logging(result.log_dir, log_level)

    # Install Qt log handler so Logs tab in settings receives live output.
    qt_log_handler = QtLogHandler()
    logging.getLogger().addHandler(qt_log_handler)

    if result.was_first_run:
        logger.info("first run: created config at %s", result.config_path)

    if result.config_error is not None:
        logger.warning("config error: %s", result.config_error)

    tray_icon = TrayIcon(config_path=result.config_path)
    companion = CompanionWidget()
    history = HistoryWindow()
    text_input = TextInputWidget()

    # Apply lerp factor from config.
    if result.config is not None:
        companion.set_lerp_factor(result.config.lerp_factor)

    settings_window = SettingsWindow(
        config_path=result.config_path,
        log_handler=qt_log_handler,
    )

    mic = MicCapture()
    output_capture = OutputCapture()

    mic.error.connect(lambda msg: logger.error("mic error: %s", msg))
    output_capture.audio_level.connect(companion.set_output_level)

    # Tray → settings window (replaces os.startfile).
    tray_icon.show_settings_requested.connect(settings_window.show)
    tray_icon.show_settings_requested.connect(settings_window.raise_)

    # Tray → history window.
    tray_icon.show_history_requested.connect(history.show)
    tray_icon.show_history_requested.connect(history.raise_)

    # ------------------------------------------------------------------
    # Hotkey monitor
    # ------------------------------------------------------------------
    hotkey_binding = result.config.hotkey if result.config is not None else "ctrl+alt"
    hotkey_monitor = HotkeyMonitor(binding=hotkey_binding)

    # Text input mode: Shift+hotkey shows the floating textbox.
    def _on_text_input_requested() -> None:
        pos = companion.pos()
        text_input.show_near(pos.x(), pos.y() + companion.height() + 4)

    hotkey_monitor.text_input_requested.connect(_on_text_input_requested)

    # ------------------------------------------------------------------
    # Mutable container so provider_changed can swap the manager.
    # ------------------------------------------------------------------
    _manager: list[CompanionManager | None] = [None]

    def _wire_manager(mgr: CompanionManager) -> None:
        """Connect a freshly-created manager to all UI slots."""
        mgr.state_changed.connect(companion.set_state)

        def _manage_output_capture(state: VoiceState) -> None:
            if state == VoiceState.RESPONDING:
                output_capture.start()
            else:
                output_capture.stop()

        mgr.state_changed.connect(_manage_output_capture)
        mgr.audio_level.connect(companion.set_audio_level)
        mgr.final_transcript.connect(
            lambda text: logger.info("final transcript: %s", text)
        )
        mgr.response_complete.connect(
            lambda text: logger.info("response complete: %s", text[:120])
        )
        mgr.error.connect(lambda msg: logger.error("error: %s", msg))
        mgr.error.connect(companion.flash_error)

        # History window.
        mgr.interim_transcript.connect(history.append_interim)
        mgr.final_transcript.connect(history.set_final)
        mgr.response_delta.connect(history.append_delta)
        mgr.response_complete.connect(history.commit_turn)
        mgr.error.connect(history.show_error)

        # Settings window history tab.
        mgr.interim_transcript.connect(settings_window.history_widget.append_interim)
        mgr.final_transcript.connect(settings_window.history_widget.set_final)
        mgr.response_delta.connect(settings_window.history_widget.append_delta)
        mgr.response_complete.connect(settings_window.history_widget.commit_turn)
        mgr.error.connect(settings_window.history_widget.show_error)

    def _build_manager(config: Config) -> CompanionManager | None:
        try:
            transcription = TranscriptionClient(worker_url=config.worker_url)
            llm = LLMClient(worker_url=config.worker_url)
            tts = TTSClient(worker_url=config.worker_url)
        except Exception as exc:
            logger.error("Failed to create AI clients: %s", exc)
            return None

        mgr = CompanionManager(
            config=config,
            mic=mic,
            hotkey=hotkey_monitor,
            transcription=transcription,
            llm=llm,
            tts=tts,
            screen_capture_fn=capture_all,
            panel_visibility_controller=companion,
        )
        _wire_manager(mgr)
        logger.info("AI clients initialised (worker_url=%s)", config.worker_url)
        return mgr

    if result.config is not None:
        _manager[0] = _build_manager(result.config)

    def _on_provider_changed() -> None:
        """Reload config and reinitialise AI clients after a provider switch."""
        try:
            new_config = Config.from_path(result.config_path)
        except ConfigError as exc:
            logger.error("Config reload failed: %s", exc)
            return

        old = _manager[0]
        if old is not None:
            old.deleteLater()

        _manager[0] = _build_manager(new_config)
        companion.set_lerp_factor(new_config.lerp_factor)
        tray_icon.showMessage("ClickyWin", "Provider settings saved — restart may be required.")

    tray_icon.provider_changed.connect(_on_provider_changed)
    settings_window.provider_changed.connect(_on_provider_changed)

    def _on_settings_saved() -> None:
        """Apply general settings changes that don't need a full client restart."""
        try:
            new_config = Config.from_path(result.config_path)
        except ConfigError as exc:
            logger.error("Config reload failed: %s", exc)
            return
        companion.set_lerp_factor(new_config.lerp_factor)
        tray_icon.showMessage("ClickyWin", "General settings saved.")

    settings_window.settings_saved.connect(_on_settings_saved)

    # Text input submitted → run turn directly via manager.
    def _on_text_submitted(text: str) -> None:
        mgr = _manager[0]
        if mgr is not None:
            companion.set_state(VoiceState.PROCESSING)
            mgr.handle_text_input(text)

    text_input.submitted.connect(_on_text_submitted)
    text_input.cancelled.connect(lambda: companion.set_state(VoiceState.IDLE))

    hotkey_monitor.start()
    tray_icon.show()
    companion.show()

    result.app.aboutToQuit.connect(hotkey_monitor.stop)
    result.app.aboutToQuit.connect(companion.hide)
    result.app.aboutToQuit.connect(output_capture.stop)

    loop = qasync.QEventLoop(result.app)
    asyncio.set_event_loop(loop)

    signal.signal(signal.SIGINT, lambda *_: result.app.quit())

    with loop:
        loop.run_forever()
    return 0
