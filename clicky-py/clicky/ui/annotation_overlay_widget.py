"""Screen annotation overlay — animated circle that draws around a POINT target."""
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
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from clicky.design_system import DS
from clicky.ui.win32_transparency import apply_win32_transparency

_CIRCLE_RADIUS = 28.0
_PULSE_RADIUS_MAX = 54.0
_PEN_WIDTH = 2.5


class AnnotationOverlayWidget(QWidget):
    """Fullscreen overlay: strokes a circle around a POINT then fades out."""

    _DRAW_DURATION_MS = 320
    _FADE_DURATION_MS = 850

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

        self._cx: float = 0.0
        self._cy: float = 0.0
        self._draw_progress: float = 0.0
        self._annotation_opacity: float = 1.0

        self._draw_anim = QPropertyAnimation(self, b"draw_progress")
        self._draw_anim.setDuration(self._DRAW_DURATION_MS)
        self._draw_anim.setStartValue(0.0)
        self._draw_anim.setEndValue(1.0)
        self._draw_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_anim = QPropertyAnimation(self, b"annotation_opacity")
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

    def _get_annotation_opacity(self) -> float:
        return self._annotation_opacity

    def _set_annotation_opacity(self, val: float) -> None:
        self._annotation_opacity = val
        self.update()

    annotation_opacity = Property(float, _get_annotation_opacity, _set_annotation_opacity)

    def show_circle(self, x: int, y: int) -> None:
        """Animate a circle around (x, y) in global screen coordinates."""
        virtual = QApplication.primaryScreen().virtualGeometry()
        self._cx = float(x - virtual.x())
        self._cy = float(y - virtual.y())
        self._draw_progress = 0.0
        self._annotation_opacity = 1.0

        self._seq.stop()
        self.setGeometry(virtual)
        self.show()
        self._seq.start()

    def showEvent(self, event) -> None:  # noqa: ARG002
        if sys.platform == "win32":
            apply_win32_transparency(int(self.winId()))

    def paintEvent(self, event) -> None:  # noqa: ARG002
        if self._annotation_opacity <= 0.01 and self._draw_progress <= 0.01:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        alpha = int(255 * self._annotation_opacity)
        cx, cy = self._cx, self._cy

        # Main circle — strokes in via dash pattern growing from 0 to full circumference.
        circumference = 2.0 * math.pi * _CIRCLE_RADIUS
        drawn = max(0.5, circumference * self._draw_progress)
        remaining = circumference - drawn

        pen = QPen(QColor(DS.Colors.accent_blue))
        pen.setWidthF(_PEN_WIDTH)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.color().setAlpha(alpha)

        # Rebuild color with correct alpha each frame.
        c = QColor(DS.Colors.accent_blue)
        c.setAlpha(alpha)
        pen.setColor(c)

        if self._draw_progress >= 0.999:
            pen.setStyle(Qt.PenStyle.SolidLine)
        else:
            pen.setStyle(Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([drawn, max(0.5, remaining)])

        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), _CIRCLE_RADIUS, _CIRCLE_RADIUS)

        # Expanding pulse ring — grows outward as circle draws in, fades with it.
        pulse_r = _CIRCLE_RADIUS + (_PULSE_RADIUS_MAX - _CIRCLE_RADIUS) * self._draw_progress
        pulse_alpha = int(110 * self._annotation_opacity * (1.0 - self._draw_progress * 0.6))
        if pulse_alpha > 2:
            pulse_c = QColor(DS.Colors.accent_blue)
            pulse_c.setAlpha(pulse_alpha)
            pulse_pen = QPen(pulse_c)
            pulse_pen.setWidthF(1.0)
            pulse_pen.setCosmetic(True)
            painter.setPen(pulse_pen)
            painter.drawEllipse(QPointF(cx, cy), pulse_r, pulse_r)

        painter.end()
