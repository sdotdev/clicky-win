"""Streaming text output panel — slides open when AI responds."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import QPlainTextEdit, QProgressBar, QVBoxLayout, QWidget

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

        self._progress_bar = QProgressBar(self)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(5)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {DS.Colors.surface};
                border: none;
                border-radius: 2px;
                margin: 0px 8px 6px 8px;
            }}
            QProgressBar::chunk {{
                background-color: {DS.Colors.accent_blue};
                border-radius: 2px;
            }}
        """)
        self._progress_bar.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._text_edit)
        layout.addWidget(self._progress_bar)

        self._geom_anim = QPropertyAnimation(self, b"geometry")
        self._geom_anim.setDuration(self.ANIM_DURATION_MS)
        self._geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._geom_anim.finished.connect(lambda: self.setFixedSize(self.WIDTH, self.HEIGHT))

        # Drag state
        self._drag_offset: QPoint | None = None

    # ------------------------------------------------------------------
    # Drag to move
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Progress bar
    # ------------------------------------------------------------------

    def set_progress(self, current: int, total: int) -> None:
        """Show step progress. Hides bar for single-step responses."""
        if total > 1:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(current)
            self._progress_bar.show()
        else:
            self._progress_bar.hide()

    # ------------------------------------------------------------------
    # Animation + content
    # ------------------------------------------------------------------

    def show_animated(self, anchor_x: int, anchor_y: int) -> None:
        """Animate the widget growing from (anchor_x, anchor_y) down-right."""
        self._text_edit.clear()
        self._progress_bar.hide()
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
        self._progress_bar.hide()
        self.hide()
