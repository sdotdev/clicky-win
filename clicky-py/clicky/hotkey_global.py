"""Fixed-combo global shortcuts for app-level actions.

Keybinds (cannot conflict with the PTT ctrl+alt system):
    Ctrl+Shift+,  — open settings
    Ctrl+Shift+Q  — quit

Uses pynput GlobalHotKeys which handles combo matching internally.
Signals are marshalled to the Qt main thread via QueuedConnection.
"""

from __future__ import annotations

from pynput import keyboard
from PySide6.QtCore import QMetaObject, QObject, Qt, Signal, Slot


class GlobalShortcutMonitor(QObject):
    open_settings = Signal()
    quit_app = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listener: keyboard.GlobalHotKeys | None = None

    def start(self) -> None:
        """Install global shortcut hooks. Idempotent."""
        if self._listener is not None:
            return
        self._listener = keyboard.GlobalHotKeys({
            "<ctrl>+<shift>+,": self._on_open_settings,
            "<ctrl>+<shift>+q": self._on_quit,
        })
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    # pynput callbacks run on the listener thread — marshal to main thread.
    def _on_open_settings(self) -> None:
        QMetaObject.invokeMethod(self, "_emit_open_settings", Qt.ConnectionType.QueuedConnection)

    def _on_quit(self) -> None:
        QMetaObject.invokeMethod(self, "_emit_quit_app", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _emit_open_settings(self) -> None:
        self.open_settings.emit()

    @Slot()
    def _emit_quit_app(self) -> None:
        self.quit_app.emit()
