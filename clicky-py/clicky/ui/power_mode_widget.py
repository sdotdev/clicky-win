"""Power Mode — the viral "code in the dark" effect, for your whole desktop.

A fullscreen, click-through overlay that turns ordinary mouse use into a show:
every move trails glowing sparks, every click detonates a colour burst with a
shockwave ring and a screen shake, and a combo meter in the top-centre climbs
(and colour-shifts) the faster you go. Pure visuals — no AI, no network.
"""

from __future__ import annotations

import contextlib
import logging
import random
import sys
import time
from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QPainter,
    QPainterPath,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget

from clicky.design_system import DS, hsv_color
from clicky.effects.particles import (
    Particle,
    spawn_burst,
    spawn_trail_spark,
    step_all,
)
from clicky.ui.win32_transparency import apply_win32_transparency

logger = logging.getLogger(__name__)

_TICK_MS = 16
_COMBO_TIMEOUT_S = 1.6          # combo resets if no click within this window
_TRAIL_MIN_MOVE_PX = 6          # cursor must move this far to emit a spark
_MAX_PARTICLES = 1400           # safety cap


@dataclass
class _Shockwave:
    x: float
    y: float
    age: float = 0.0
    max_age: float = 0.6
    color: tuple[int, int, int] = (120, 180, 255)


class PowerModeWidget(QWidget):
    """Fullscreen transparent overlay rendering the Power Mode effect."""

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

        self._rng = random.Random()
        self._particles: list[Particle] = []
        self._shockwaves: list[_Shockwave] = []
        self._ox = 0
        self._oy = 0

        # Combo state
        self._combo = 0
        self._combo_best = 0
        self._last_click_t = 0.0
        self._combo_pop = 0.0       # 0..1 scale-pop after each increment
        self._meter_alpha = 0.0     # fades the whole meter in/out

        # Screen shake
        self._shake = 0.0

        # Cursor trail tracking
        self._prev_cursor: tuple[int, int] | None = None

        # Thread-safe queue of click positions from the global listener.
        self._pending_clicks: deque[tuple[int, int]] = deque()
        self._mouse_listener = None
        self._enabled = False

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Enable / disable
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

    def _enable(self) -> None:
        self._enabled = True
        virtual = QApplication.primaryScreen().virtualGeometry()
        self._ox, self._oy = virtual.x(), virtual.y()
        self.setGeometry(virtual)
        self._prev_cursor = None
        self._meter_alpha = 0.0
        self.show()
        self._timer.start()
        self._start_mouse_listener()
        # A welcome burst at the cursor so the effect announces itself.
        self.demo_burst()
        logger.info("Power Mode enabled")

    def _disable(self) -> None:
        self._enabled = False
        self._timer.stop()
        self._stop_mouse_listener()
        self._particles.clear()
        self._shockwaves.clear()
        self._combo = 0
        self.hide()
        logger.info("Power Mode disabled")

    # ------------------------------------------------------------------
    # Global mouse listener (clicks). Best-effort — guarded for headless.
    # ------------------------------------------------------------------

    def _start_mouse_listener(self) -> None:
        try:
            from pynput import mouse
        except Exception as exc:  # noqa: BLE001
            logger.warning("Power Mode: pynput unavailable (%s); clicks disabled", exc)
            return

        def on_click(x, y, _button, pressed):  # noqa: ANN001
            if pressed:
                self._pending_clicks.append((int(x), int(y)))

        try:
            self._mouse_listener = mouse.Listener(on_click=on_click)
            self._mouse_listener.start()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Power Mode: could not start mouse listener (%s)", exc)
            self._mouse_listener = None

    def _stop_mouse_listener(self) -> None:
        if self._mouse_listener is not None:
            with contextlib.suppress(Exception):
                self._mouse_listener.stop()
            self._mouse_listener = None
        self._pending_clicks.clear()

    # ------------------------------------------------------------------
    # Public: trigger a burst manually (used on enable + for previews/demo)
    # ------------------------------------------------------------------

    def demo_burst(self) -> None:
        pos = QCursor.pos()
        self._detonate(pos.x(), pos.y())

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def _combo_color(self) -> tuple[int, int, int]:
        """Colour escalates through the spectrum as the combo climbs."""
        hue = (0.58 - min(self._combo, 40) / 40.0 * 0.58) % 1.0  # blue → red
        return hsv_color(hue, sat=0.85, val=1.0)

    def _detonate(self, screen_x: int, screen_y: int) -> None:
        """Click burst: particles + shockwave + shake + combo increment."""
        lx = float(screen_x - self._ox)
        ly = float(screen_y - self._oy)

        now = time.monotonic()
        if now - self._last_click_t <= _COMBO_TIMEOUT_S:
            self._combo += 1
        else:
            self._combo = 1
        self._last_click_t = now
        self._combo_best = max(self._combo_best, self._combo)
        self._combo_pop = 1.0
        self._meter_alpha = 1.0

        intensity = min(1.0, 0.4 + self._combo * 0.06)
        count = int(26 + intensity * 46)
        self._particles.extend(
            spawn_burst(
                lx, ly, count, DS.POWER_PALETTE,
                speed=420.0 + intensity * 360.0,
                life=0.8 + intensity * 0.5,
                size=3.5 + intensity * 2.5,
                drag=0.14,
                rng=self._rng,
            )
        )
        if len(self._particles) > _MAX_PARTICLES:
            self._particles = self._particles[-_MAX_PARTICLES:]

        self._shockwaves.append(
            _Shockwave(x=lx, y=ly, color=self._combo_color(),
                       max_age=0.55 + intensity * 0.2)
        )
        self._shake = min(16.0, self._shake + 6.0 + intensity * 8.0)

    def _tick(self) -> None:
        dt = _TICK_MS / 1000.0
        now = time.monotonic()

        # Drain queued clicks from the listener thread.
        while self._pending_clicks:
            cx, cy = self._pending_clicks.popleft()
            self._detonate(cx, cy)

        # Cursor-movement trail sparks.
        pos = QCursor.pos()
        cur = (pos.x(), pos.y())
        if self._prev_cursor is not None:
            dx = cur[0] - self._prev_cursor[0]
            dy = cur[1] - self._prev_cursor[1]
            dist = (dx * dx + dy * dy) ** 0.5
            if dist >= _TRAIL_MIN_MOVE_PX:
                n = min(6, 1 + int(dist / 24))
                for _ in range(n):
                    self._particles.append(
                        spawn_trail_spark(
                            cur[0] - self._ox, cur[1] - self._oy,
                            DS.POWER_PALETTE, rng=self._rng,
                        )
                    )
        self._prev_cursor = cur

        # Combo decay.
        if self._combo > 0 and now - self._last_click_t > _COMBO_TIMEOUT_S:
            self._combo = 0
        if self._combo == 0:
            self._meter_alpha = max(0.0, self._meter_alpha - dt * 1.6)
        self._combo_pop = max(0.0, self._combo_pop - dt * 4.0)

        # Physics.
        self._particles = step_all(self._particles, dt)
        for w in self._shockwaves:
            w.age += dt
        self._shockwaves = [w for w in self._shockwaves if w.age < w.max_age]

        # Shake decay.
        self._shake = max(0.0, self._shake - dt * 60.0)

        self.update()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: ARG002, N802
        if sys.platform == "win32":
            apply_win32_transparency(int(self.winId()))

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._shake > 0.2:
            painter.translate(
                self._rng.uniform(-self._shake, self._shake),
                self._rng.uniform(-self._shake, self._shake),
            )

        self._paint_shockwaves(painter)
        self._paint_particles(painter)
        painter.resetTransform()
        self._paint_combo_meter(painter)
        painter.end()

    def _paint_shockwaves(self, painter: QPainter) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for w in self._shockwaves:
            t = w.age / w.max_age
            radius = 12.0 + t * 150.0
            alpha = int((1.0 - t) ** 2 * 200)
            if alpha <= 2:
                continue
            from PySide6.QtGui import QPen
            pen = QPen(QColor(w.color[0], w.color[1], w.color[2], alpha))
            pen.setWidthF(max(1.0, 5.0 * (1.0 - t)))
            painter.setPen(pen)
            painter.drawEllipse(QPointF(w.x, w.y), radius, radius)

    def _paint_particles(self, painter: QPainter) -> None:
        # Additive blending gives the bright, layered "glow" look.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setPen(Qt.PenStyle.NoPen)
        for p in self._particles:
            a = p.alpha
            if a <= 0.02 or p.size <= 0.2:
                continue
            r, g, b = p.color
            cx, cy = p.x, p.y

            # Soft halo.
            halo_r = p.size * 3.2
            grad = QRadialGradient(QPointF(cx, cy), halo_r)
            grad.setColorAt(0.0, QColor(r, g, b, int(150 * a)))
            grad.setColorAt(0.4, QColor(r, g, b, int(60 * a)))
            grad.setColorAt(1.0, QColor(r, g, b, 0))
            painter.setBrush(grad)
            painter.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

            # Bright core.
            painter.setBrush(QColor(
                min(255, r + 80), min(255, g + 80), min(255, b + 80),
                int(235 * a),
            ))
            painter.drawEllipse(QPointF(cx, cy), p.size, p.size)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    def _paint_combo_meter(self, painter: QPainter) -> None:
        if self._meter_alpha <= 0.02 or self._combo <= 0:
            return
        r, g, b = self._combo_color()
        alpha = self._meter_alpha
        cx = self.width() / 2.0
        cy = 96.0

        pop = 1.0 + self._combo_pop * 0.35
        big_size = int(54 * pop)

        # Glow halo behind the number.
        painter.setPen(Qt.PenStyle.NoPen)
        glow = QRadialGradient(QPointF(cx, cy), 150 * pop)
        glow.setColorAt(0.0, QColor(r, g, b, int(150 * alpha)))
        glow.setColorAt(1.0, QColor(r, g, b, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), 150 * pop, 150 * pop)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # The combo number (drawn as a filled path so it glows crisply).
        number_font = QFont(DS.Fonts.family_ui, big_size, QFont.Weight.Black)
        number_font.setItalic(True)
        path = QPainterPath()
        text = f"{self._combo}×"
        path.addText(0, 0, number_font, text)
        br = path.boundingRect()
        painter.save()
        painter.translate(cx - br.center().x(), cy - br.center().y())
        # Outline glow.
        from PySide6.QtGui import QPen
        outline = QPen(QColor(r, g, b, int(220 * alpha)))
        outline.setWidthF(6.0)
        painter.setPen(outline)
        painter.setBrush(QColor(255, 255, 255, int(245 * alpha)))
        painter.drawPath(path)
        painter.restore()

        # "COMBO" caption + decay bar.
        cap_font = QFont(DS.Fonts.family_ui, 13, QFont.Weight.Bold)
        cap_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4.0)
        painter.setFont(cap_font)
        painter.setPen(QColor(r, g, b, int(230 * alpha)))
        cap_rect = QRectF(cx - 200, cy + 34, 400, 24)
        label = "POWER MODE" if self._combo >= 10 else "COMBO"
        painter.drawText(cap_rect, Qt.AlignmentFlag.AlignCenter, label)

        # Decay timer bar.
        remaining = max(
            0.0, 1.0 - (time.monotonic() - self._last_click_t) / _COMBO_TIMEOUT_S
        )
        bar_w = 150.0
        bar_x = cx - bar_w / 2.0
        bar_y = cy + 62.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, int(40 * alpha)))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, 4), 2, 2)
        painter.setBrush(QColor(r, g, b, int(230 * alpha)))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w * remaining, 4), 2, 2)
