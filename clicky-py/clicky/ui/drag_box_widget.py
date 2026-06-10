"""Animated drag-selection rectangle shown during text-input open animation."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class DragBoxWidget(QWidget):
    """Hollow orange dashed rectangle that grows from an anchor point.

    Shown in parallel with CompanionWidget.drag_open() to give a drag-selection
    feel when the text input box is opened.  Auto-hides when the animation ends.
    """

    BORDER_COLOR = "#FF6B00"
    BORDER_WIDTH = 2
    ANIM_DURATION_MS = 280

    def __init__(self, target_w: int, target_h: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target_w = target_w
        self._target_h = target_h

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._geom_anim = QPropertyAnimation(self, b"geometry")
        self._geom_anim.setDuration(self.ANIM_DURATION_MS)
        self._geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._geom_anim.finished.connect(self.hide)

    def show_drag(self, anchor_x: int, anchor_y: int) -> None:
        """Grow from a 1×1 point at (anchor_x, anchor_y) to full target size."""
        self._geom_anim.stop()
        self.setGeometry(QRect(anchor_x, anchor_y, 1, 1))
        self.show()
        self._geom_anim.setStartValue(QRect(anchor_x, anchor_y, 1, 1))
        self._geom_anim.setEndValue(QRect(anchor_x, anchor_y, self._target_w, self._target_h))
        self._geom_anim.start()

    def paintEvent(self, event) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(self.BORDER_COLOR))
        pen.setWidth(self.BORDER_WIDTH)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern([6, 4])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        inset = self.BORDER_WIDTH
        painter.drawRect(
            inset, inset,
            self.width() - inset * 2,
            self.height() - inset * 2,
        )
