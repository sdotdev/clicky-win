"""Streaming text output panel — slides open when AI responds."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from clicky.design_system import DS


class OutputWidget(QWidget):
    """Frameless floating output panel. Slides open when the AI starts responding."""

    WIDTH = 300
    HEIGHT = 300
    ANIM_DURATION_MS = 280

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("OutputWidget")

        self.setStyleSheet(f"""
            QWidget#OutputWidget {{
                background-color: {DS.Colors.panel_bg};
                border-radius: 8px;
                border: 1px solid {DS.Colors.border};
            }}
        """)

        self._text_edit = QPlainTextEdit(self)
        self._text_edit.setReadOnly(True)
        self._text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._text_edit.setFont(QFont("Segoe UI", 10))
        self._text_edit.setStyleSheet(
            f"background: transparent; color: {DS.Colors.text_primary}; border: none; padding: 8px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._text_edit)

        self._geom_anim = QPropertyAnimation(self, b"geometry")
        self._geom_anim.setDuration(self.ANIM_DURATION_MS)
        self._geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._geom_anim.finished.connect(lambda: self.setFixedSize(self.WIDTH, self.HEIGHT))

    def show_animated(self, anchor_x: int, anchor_y: int) -> None:
        """Animate the widget growing from (anchor_x, anchor_y) down-right."""
        self._text_edit.clear()
        # Release fixed-size constraints so the geometry animation can resize freely.
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._geom_anim.stop()
        self.setGeometry(QRect(anchor_x, anchor_y, 1, 1))
        self.show()
        self._geom_anim.setStartValue(QRect(anchor_x, anchor_y, 1, 1))
        self._geom_anim.setEndValue(QRect(anchor_x, anchor_y, self.WIDTH, self.HEIGHT))
        self._geom_anim.start()

    def append_delta(self, text: str) -> None:
        """Append a streaming chunk and scroll to bottom."""
        self._text_edit.insertPlainText(text)
        sb = self._text_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_text(self, text: str) -> None:
        """Replace the full text content and scroll to bottom."""
        self._text_edit.setPlainText(text)
        sb = self._text_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_and_hide(self) -> None:
        """Clear text and hide the widget."""
        self._text_edit.clear()
        self.hide()
