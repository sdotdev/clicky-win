"""Floating text input widget for keyboard-driven queries."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from clicky.design_system import DS


class TextInputWidget(QWidget):
    """Frameless floating text input. Appears near companion on Shift+hotkey."""

    submitted = Signal(str)
    cancelled = Signal()

    WIDTH = 320
    HEIGHT = 36

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        self._edit = QLineEdit(self)
        self._edit.setPlaceholderText("Type your query…")
        self._edit.setFont(QFont("Segoe UI", 11))
        self._edit.installEventFilter(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self._edit)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {DS.Colors.surface};
                border: 1px solid {DS.Colors.accent_blue};
                border-radius: 6px;
            }}
            QLineEdit {{
                background: transparent;
                border: none;
                color: {DS.Colors.text_primary};
                padding: 2px 4px;
            }}
        """)

    def show_near(self, x: int, y: int) -> None:
        """Show the widget near the given screen coordinates."""
        self._edit.clear()
        self.move(x, y)
        self.show()
        self.activateWindow()
        self._edit.setFocus()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._edit and isinstance(event, QKeyEvent):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                text = self._edit.text().strip()
                if text:
                    self.submitted.emit(text)
                self.hide()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.cancelled.emit()
                self.hide()
                return True
        return super().eventFilter(obj, event)
