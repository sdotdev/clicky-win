"""Live Click Heatmap overlay — glowing heatmap of click positions over the desktop.

Records every mouse click and paints a glowing radial heatmap on top of the
desktop. Recent clicks are warm (orange/red), older clicks fade to cool
(blue/cyan). Activated with /heatmap.
"""

from __future__ import annotations

import contextlib
import logging
import sys
import time
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget

from clicky.design_system import DS, hex_to_rgb, lerp_color
from clicky.ui.win32_transparency import apply_win32_transparency

logger = logging.getLogger(__name__)

_TICK_MS = 33
_MAX_CLICKS = 800
_CLICK_MAX_AGE_S = 45.0


class HeatmapOverlayWidget(QWidget):
    """Fullscreen transparent overlay rendering a live click heatmap."""

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
        self.setStyleSheet("background:transparent;")

        # Click history: (local_x, local_y, monotonic_timestamp)
        self._clicks: deque[tuple[float, float, float]] = deque(maxlen=_MAX_CLICKS)

        # Thread-safe queue of raw screen positions from pynput
        self._pending_clicks: deque[tuple[int, int]] = deque()

        self._mouse_listener = None
        self._enabled: bool = False
        self._fade_alpha: float = 0.0

        # Virtual geometry origin (so local coords map to the overlay)
        self._ox: float = 0.0
        self._oy: float = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, on: bool) -> None:
        if on == self._enabled:
            return
        if on:
            self._enable()
        else:
            self._disable()

    def toggle(self) -> bool:
        self.set_enabled(not self._enabled)
        return self._enabled

    # ------------------------------------------------------------------
    # Enable / disable internals
    # ------------------------------------------------------------------

    def _enable(self) -> None:
        self._enabled = True
        virtual = QApplication.primaryScreen().virtualGeometry()
        self._ox, self._oy = float(virtual.x()), float(virtual.y())
        self.setGeometry(virtual)
        self.show()
        self._timer.start()
        self._start_mouse_listener()
        logger.info("Heatmap overlay enabled")

    def _disable(self) -> None:
        self._enabled = False
        self._stop_mouse_listener()
        # _fade_alpha fades to 0 in _tick, then hides
        logger.info("Heatmap overlay disabled")

    # ------------------------------------------------------------------
    # Global mouse listener (pynput) — best-effort, guarded for headless
    # ------------------------------------------------------------------

    def _start_mouse_listener(self) -> None:
        try:
            from pynput import mouse
        except Exception as exc:  # noqa: BLE001
            logger.warning("Heatmap: pynput unavailable (%s); clicks disabled", exc)
            return

        def on_click(x, y, _button, pressed):  # noqa: ANN001
            if pressed:
                self._pending_clicks.append((int(x), int(y)))

        try:
            self._mouse_listener = mouse.Listener(on_click=on_click)
            self._mouse_listener.start()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Heatmap: could not start mouse listener (%s)", exc)
            self._mouse_listener = None

    def _stop_mouse_listener(self) -> None:
        if self._mouse_listener is not None:
            with contextlib.suppress(Exception):
                self._mouse_listener.stop()
            self._mouse_listener = None
        self._pending_clicks.clear()

    # ------------------------------------------------------------------
    # Simulation tick
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        now = time.monotonic()

        # Drain pending clicks from the listener thread
        while self._pending_clicks:
            cx, cy = self._pending_clicks.popleft()
            lx = cx - self._ox
            ly = cy - self._oy
            self._clicks.append((lx, ly, now))

        # Fade in / out
        target_alpha = 1.0 if self._enabled else 0.0
        self._fade_alpha += (target_alpha - self._fade_alpha) * 0.15
        if not self._enabled and self._fade_alpha < 0.01:
            self._fade_alpha = 0.0
            self._timer.stop()
            self.hide()
            return

        # Prune clicks older than 45 seconds
        self._clicks = deque(
            ((x, y, t) for x, y, t in self._clicks if now - t < _CLICK_MAX_AGE_S),
            maxlen=_MAX_CLICKS,
        )
        self.update()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: ARG002, N802
        if sys.platform == "win32":
            apply_win32_transparency(int(self.winId()))

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        if self._fade_alpha < 0.01 or not self._clicks:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        now = time.monotonic()

        for x, y, t in self._clicks:
            age = now - t  # seconds old
            recency = max(0.0, 1.0 - age / _CLICK_MAX_AGE_S)  # 1.0=fresh, 0.0=old

            # Color: interpolate cool → hot based on recency
            # Hot (recent): orange-red  Cold (old): blue-cyan
            r, g, b = lerp_color("#00b4ff", "#ff4500", recency)

            # Alpha: bright when fresh, fades with age
            base_alpha = recency * 0.85 + 0.12  # always slightly visible
            global_a = self._fade_alpha

            # Large outer halo (big, soft, low alpha — accumulates with additive blending)
            outer_r = 55.0
            grad = QRadialGradient(QPointF(x, y), outer_r)
            grad.setColorAt(0.0, QColor(r, g, b, int(55 * base_alpha * global_a)))
            grad.setColorAt(0.5, QColor(r, g, b, int(28 * base_alpha * global_a)))
            grad.setColorAt(1.0, QColor(r, g, b, 0))
            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(x, y), outer_r, outer_r)

            # Inner bright core
            inner_r = 12.0
            grad2 = QRadialGradient(QPointF(x, y), inner_r)
            grad2.setColorAt(
                0.0,
                QColor(
                    min(255, r + 80),
                    min(255, g + 80),
                    min(255, b + 80),
                    int(200 * base_alpha * global_a),
                ),
            )
            grad2.setColorAt(1.0, QColor(r, g, b, 0))
            painter.setBrush(grad2)
            painter.drawEllipse(QPointF(x, y), inner_r, inner_r)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # HUD label: bottom-left
        cr, cg, cb = hex_to_rgb(DS.Colors.neon_cyan)
        font = QFont("Consolas", 11, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        painter.setFont(font)
        painter.setPen(QColor(cr, cg, cb, int(200 * self._fade_alpha)))
        painter.drawText(
            QRectF(20, self.height() - 50, 400, 30),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"◈ HEATMAP  \xb7  {len(self._clicks)} clicks",
        )
        painter.end()
