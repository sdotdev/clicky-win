"""Fullscreen comet trail overlay — short glowing trail following the companion."""
from __future__ import annotations

import math
import sys
from collections import deque

from PySide6.QtCore import Property, QEasingCurve, QPointF, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from clicky.ui.win32_transparency import apply_win32_transparency

_MAX_TRAIL_PX = 90    # max path length kept in buffer
_MAX_HEAD_R = 5.5     # radius of trail at the head
_FADE_DELAY_MS = 120
_FADE_DURATION_MS = 350


class CometTrailWidget(QWidget):
    """Fullscreen transparent overlay: short dot-trail that follows fly_to."""

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

        # (widget-local x, widget-local y)
        self._positions: deque[tuple[float, float]] = deque()
        self._trail_opacity: float = 1.0
        self._ox: int = 0  # virtual desktop origin x
        self._oy: int = 0  # virtual desktop origin y

        self._fade_anim = QPropertyAnimation(self, b"trail_opacity")
        self._fade_anim.setDuration(_FADE_DURATION_MS)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade_anim.finished.connect(self.hide)

        self._fade_delay = QTimer(self)
        self._fade_delay.setSingleShot(True)
        self._fade_delay.setInterval(_FADE_DELAY_MS)
        self._fade_delay.timeout.connect(self._begin_fade)

    def _get_trail_opacity(self) -> float:
        return self._trail_opacity

    def _set_trail_opacity(self, val: float) -> None:
        self._trail_opacity = val
        self.update()

    trail_opacity = Property(float, _get_trail_opacity, _set_trail_opacity)

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    def show_trail(self, sx: int, sy: int, _ex: int = 0, _ey: int = 0) -> None:
        """Called on fly_started — reset buffer and show widget."""
        virtual = QApplication.primaryScreen().virtualGeometry()
        self._ox, self._oy = virtual.x(), virtual.y()
        self._positions.clear()
        self._positions.append((float(sx - self._ox), float(sy - self._oy)))
        self._trail_opacity = 1.0
        self._fade_anim.stop()
        self._fade_delay.stop()
        self.setGeometry(virtual)
        self.show()

    def add_position(self, cx: int, cy: int) -> None:
        """Called each animation frame with the companion's screen-centre."""
        lx = float(cx - self._ox)
        ly = float(cy - self._oy)
        self._positions.append((lx, ly))
        self._trim_to_max_length()
        self.update()

    def start_fade(self, _x: int = 0, _y: int = 0) -> None:
        """Called on fly_completed — wait briefly then fade out."""
        self._fade_delay.start()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _trim_to_max_length(self) -> None:
        """Drop tail positions so total path length stays <= _MAX_TRAIL_PX."""
        while len(self._positions) > 2:
            total = sum(
                math.hypot(
                    self._positions[i + 1][0] - self._positions[i][0],
                    self._positions[i + 1][1] - self._positions[i][1],
                )
                for i in range(len(self._positions) - 1)
            )
            if total <= _MAX_TRAIL_PX:
                break
            self._positions.popleft()

    def _begin_fade(self) -> None:
        self._fade_anim.start()

    def showEvent(self, event) -> None:  # noqa: ARG002
        if sys.platform == "win32":
            apply_win32_transparency(int(self.winId()))

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: ARG002
        n = len(self._positions)
        if n == 0 or self._trail_opacity <= 0.01:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        op = self._trail_opacity

        for i, (px, py) in enumerate(self._positions):
            # t=0 at tail, t=1 at head
            t = i / max(1, n - 1)
            t2 = t * t  # quadratic — drops off fast near tail

            radius = 0.4 + t * _MAX_HEAD_R
            alpha = int(t2 * 210 * op)
            if alpha < 2:
                continue

            # Colour: blue → near-white at head
            r = int(74 + t * (220 - 74))
            g = int(158 + t * (230 - 158))
            b = 255
            painter.setBrush(QColor(r, g, b, alpha))
            painter.drawEllipse(QPointF(px, py), radius, radius)

        # Extra bright tip at head
        if n >= 1:
            hx, hy = self._positions[-1]
            tip_alpha = int(240 * op)
            painter.setBrush(QColor(240, 248, 255, tip_alpha))
            painter.drawEllipse(QPointF(hx, hy), 2.5, 2.5)

        painter.end()
