"""Screen arrow overlay — animated arrow that draws from start to end for ARROW steps."""
from __future__ import annotations

import math
import sys

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from clicky.design_system import DS
from clicky.ui.win32_transparency import apply_win32_transparency

_PEN_WIDTH = 2.5
_HEAD_SIZE = 16.0   # arrowhead length
_HEAD_WING = 8.0    # arrowhead half-width
_HEAD_THRESHOLD = 0.82  # draw arrowhead once stroke passes this fraction


class ArrowOverlayWidget(QWidget):
    """Fullscreen overlay: strokes an arrow from start to end then fades out."""

    _DRAW_DURATION_MS = 420
    _FADE_DURATION_MS = 1000

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._sx: float = 0.0
        self._sy: float = 0.0
        self._ex: float = 0.0
        self._ey: float = 0.0
        self._draw_progress: float = 0.0
        self._arrow_opacity: float = 1.0

        self._draw_anim = QPropertyAnimation(self, b"draw_progress")
        self._draw_anim.setDuration(self._DRAW_DURATION_MS)
        self._draw_anim.setStartValue(0.0)
        self._draw_anim.setEndValue(1.0)
        self._draw_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_anim = QPropertyAnimation(self, b"arrow_opacity")
        self._fade_anim.setDuration(self._FADE_DURATION_MS)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InQuad)

        self._seq = QSequentialAnimationGroup(self)
        self._seq.addAnimation(self._draw_anim)
        self._seq.addAnimation(self._fade_anim)
        self._seq.finished.connect(self.hide)

    def _get_draw_progress(self) -> float:
        return self._draw_progress

    def _set_draw_progress(self, val: float) -> None:
        self._draw_progress = val
        self.update()

    draw_progress = Property(float, _get_draw_progress, _set_draw_progress)

    def _get_arrow_opacity(self) -> float:
        return self._arrow_opacity

    def _set_arrow_opacity(self, val: float) -> None:
        self._arrow_opacity = val
        self.update()

    arrow_opacity = Property(float, _get_arrow_opacity, _set_arrow_opacity)

    def show_arrow(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """Animate an arrow from (x1,y1) to (x2,y2) in global screen coordinates."""
        virtual = QApplication.primaryScreen().virtualGeometry()
        ox, oy = virtual.x(), virtual.y()
        self._sx = float(x1 - ox)
        self._sy = float(y1 - oy)
        self._ex = float(x2 - ox)
        self._ey = float(y2 - oy)
        self._draw_progress = 0.0
        self._arrow_opacity = 1.0

        self._seq.stop()
        self.setGeometry(virtual)
        self.show()
        self._seq.start()

    def showEvent(self, event) -> None:  # noqa: ARG002
        if sys.platform == "win32":
            apply_win32_transparency(int(self.winId()))

    def paintEvent(self, event) -> None:  # noqa: ARG002
        if self._arrow_opacity <= 0.01 and self._draw_progress <= 0.01:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        alpha = int(255 * self._arrow_opacity)
        color = QColor(DS.Colors.accent_blue)
        color.setAlpha(alpha)

        sx, sy = self._sx, self._sy
        ex, ey = self._ex, self._ey

        dx = ex - sx
        dy = ey - sy
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1.0:
            painter.end()
            return

        # Current tip position along the stroke
        t = self._draw_progress
        tip_x = sx + dx * t
        tip_y = sy + dy * t

        # Stroke line using dash pattern to animate draw-in
        drawn = max(0.5, length * t)
        remaining = max(0.5, length - drawn)

        pen = QPen(color)
        pen.setWidthF(_PEN_WIDTH)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        if t >= 0.999:
            pen.setStyle(Qt.PenStyle.SolidLine)
        else:
            pen.setStyle(Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([drawn, remaining])

        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(sx, sy), QPointF(ex, ey))

        # Arrowhead — drawn once stroke is past threshold
        if t >= _HEAD_THRESHOLD:
            head_alpha = int(alpha * min(1.0, (t - _HEAD_THRESHOLD) / (1.0 - _HEAD_THRESHOLD)))
            head_color = QColor(DS.Colors.accent_blue)
            head_color.setAlpha(head_alpha)

            nx, ny = dx / length, dy / length
            px, py = -ny, nx

            tip = QPointF(tip_x, tip_y)
            base_x = tip_x - nx * _HEAD_SIZE
            base_y = tip_y - ny * _HEAD_SIZE
            wing1 = QPointF(base_x + px * _HEAD_WING, base_y + py * _HEAD_WING)
            wing2 = QPointF(base_x - px * _HEAD_WING, base_y - py * _HEAD_WING)

            head_path = QPainterPath()
            head_path.moveTo(tip)
            head_path.lineTo(wing1)
            head_path.lineTo(wing2)
            head_path.closeSubpath()

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(head_color)
            painter.drawPath(head_path)

        painter.end()
