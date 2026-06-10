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

from clicky.clients.factory import create_brain, create_ears, create_mouth
from clicky.companion_manager import CompanionManager
from clicky.config import Config, ConfigError
from clicky.hotkey import GlobalShortcutMonitor, HotkeyMonitor
from clicky.logging_config import configure_logging
from clicky.mic_capture import MicCapture
from clicky.output_capture import OutputCapture
from clicky.screen_capture import capture_all
from clicky.state import VoiceState
from clicky.ui.companion_widget import CompanionWidget
from clicky.ui.drag_box_widget import DragBoxWidget
from clicky.ui.history_window import HistoryWindow
from clicky.ui.settings_window import QtLogHandler, SettingsWindow
from clicky.ui.output_widget import OutputWidget
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
    return Path(__file__).resolve().parent.parent / "config.example.toml"


def bootstrap(argv: list[str] | None = None) -> BootstrapResult:
    argv = argv if argv is not None else sys.argv
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_AUTHOR)
    app.setQuitOnLastWindowClosed(False)

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
    drag_box = DragBoxWidget(TextInputWidget.WIDTH, TextInputWidget.HEIGHT)
    output_widget = OutputWidget()
    output_drag_box = DragBoxWidget(OutputWidget.WIDTH, OutputWidget.HEIGHT)

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

    # Tray -> settings window (replaces os.startfile).
    tray_icon.show_settings_requested.connect(settings_window.show)
    tray_icon.show_settings_requested.connect(settings_window.raise_)
    tray_icon.show_history_requested.connect(history.show)
    tray_icon.show_history_requested.connect(history.raise_)

    hotkey_binding = result.config.hotkey if result.config is not None else "ctrl+alt"
    hotkey_monitor = HotkeyMonitor(binding=hotkey_binding)

    shortcut_monitor = GlobalShortcutMonitor()
    shortcut_monitor.open_settings.connect(settings_window.show)
    shortcut_monitor.open_settings.connect(settings_window.raise_)
    shortcut_monitor.quit_app.connect(QApplication.instance().quit)

    # Text input mode: Shift+hotkey — companion drags open the text box.
    def _on_text_input_requested() -> None:
        pos = companion.pos()
        anchor_x = pos.x()
        anchor_y = pos.y() + companion.WIDGET_H + 4
        drag_x = anchor_x + TextInputWidget.WIDTH
        drag_y = anchor_y + TextInputWidget.HEIGHT
        companion.drag_open(drag_x, drag_y)
        drag_box.show_drag(anchor_x, anchor_y)
        text_input.show_animated(anchor_x, anchor_y)

    hotkey_monitor.text_input_requested.connect(_on_text_input_requested)

    # Mutable container so the provider_changed handler can replace the manager
    _manager: list[CompanionManager | None] = [None]

    def _build_manager(config: Config) -> CompanionManager | None:
        """Instantiate AI clients and wire a fresh CompanionManager."""
        try:
            llm = create_brain(config)
            transcription = create_ears(config)
            if config.tts_enabled:
                tts = create_mouth(config)
            else:
                from clicky.clients.tts_null import NullTTSClient
                tts = NullTTSClient()
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
            screen_capture_fn=lambda: capture_all(qt_screens=QApplication.screens()),
            panel_visibility_controller=companion,
        )

        mgr.state_changed.connect(companion.set_state)

        from clicky.point_parser import parse_point_tag as _parse_pt

        mgr.response_delta.connect(output_widget.append_delta)
        mgr.response_complete.connect(lambda text: output_widget.set_text(_parse_pt(text)[0]))

        def _on_state_changed_output(state: VoiceState) -> None:
            if state == VoiceState.RESPONDING:
                pos = companion.pos()
                anchor_x = pos.x() + companion.WIDGET_W + 8
                anchor_y = pos.y()
                output_widget.clear_and_hide()
                output_drag_box.show_drag(anchor_x, anchor_y)
                output_widget.show_animated(anchor_x, anchor_y)
            elif state == VoiceState.LISTENING:
                output_widget.clear_and_hide()

        mgr.state_changed.connect(_on_state_changed_output)

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

        logger.info(
            "AI providers — brain: %s, ears: %s, mouth: %s",
            config.brain.provider,
            config.ears.provider,
            config.mouth.provider,
        )
        return mgr

    if result.config is not None:
        _manager[0] = _build_manager(result.config)

    def _on_provider_changed() -> None:
        """Reload config and reinitialize AI clients after a provider switch."""
        try:
            new_config = Config.from_path(result.config_path)
        except ConfigError as exc:
            logger.error("Config reload failed after provider switch: %s", exc)
            return

        old = _manager[0]
        if old is not None:
            # Disconnect signals by replacing with a fresh manager; old one is
            # garbage-collected once no more references exist.
            old.deleteLater()

        _manager[0] = _build_manager(new_config)
        companion.set_lerp_factor(new_config.lerp_factor)
        tray_icon.showMessage(
            "ClickyWin",
            f"Switched — brain: {new_config.brain.provider}, "
            f"ears: {new_config.ears.provider}, mouth: {new_config.mouth.provider}",
        )

    tray_icon.provider_changed.connect(_on_provider_changed)
    settings_window.provider_changed.connect(_on_provider_changed)

    def _on_settings_saved() -> None:
        """Apply general settings that do not need a full client restart."""
        try:
            new_config = Config.from_path(result.config_path)
        except ConfigError as exc:
            logger.error("Config reload failed: %s", exc)
            return
        companion.set_lerp_factor(new_config.lerp_factor)
        tray_icon.showMessage("ClickyWin", "General settings saved.")

    settings_window.settings_saved.connect(_on_settings_saved)

    # Also update lerp on provider switch.
    # Text input submitted -> run turn directly via manager.
    def _on_text_submitted(text: str) -> None:
        mgr = _manager[0]
        if mgr is not None:
            companion.set_state(VoiceState.PROCESSING)
            mgr.handle_text_input(text)

    text_input.submitted.connect(_on_text_submitted)
    text_input.cancelled.connect(lambda: companion.set_state(VoiceState.IDLE))

    hotkey_monitor.start()
    shortcut_monitor.start()
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
