"""Floating text input widget for keyboard-driven queries."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from clicky.design_system import DS


class TextInputWidget(QWidget):
    """Frameless floating text input. Appears near companion on Shift+hotkey."""

    submitted = Signal(str)
    cancelled = Signal()

    WIDTH = 320
    HEIGHT = 36
    ANIM_DURATION_MS = 280

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        # Do NOT setFixedSize here — show_animated needs to override size constraints.

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

        self._geom_anim = QPropertyAnimation(self, b"geometry")
        self._geom_anim.setDuration(self.ANIM_DURATION_MS)
        self._geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._geom_anim.finished.connect(self._on_anim_finished)
        self._anchor_x = 0
        self._anchor_y = 0

    def show_near(self, x: int, y: int) -> None:
        """Show the widget near the given screen coordinates (no animation)."""
        self._edit.clear()
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.move(x, y)
        self.show()
        self.activateWindow()
        self._edit.setFocus()

    def show_animated(self, anchor_x: int, anchor_y: int) -> None:
        """Animate the widget growing from (anchor_x, anchor_y) down-right."""
        self._anchor_x = anchor_x
        self._anchor_y = anchor_y
        self._edit.clear()
        # Release fixed-size constraints so the geometry animation can resize freely.
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._geom_anim.stop()
        self.setGeometry(QRect(anchor_x, anchor_y, 1, 1))
        self.show()
        self._geom_anim.setStartValue(QRect(anchor_x, anchor_y, 1, 1))
        self._geom_anim.setEndValue(QRect(anchor_x, anchor_y, self.WIDTH, self.HEIGHT))
        self._geom_anim.start()

    def _on_anim_finished(self) -> None:
        self.setFixedSize(self.WIDTH, self.HEIGHT)
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
