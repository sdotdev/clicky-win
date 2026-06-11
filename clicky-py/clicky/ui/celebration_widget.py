"""Celebration overlay — fullscreen fireworks and confetti.

Launches a flurry of firework shells that rise on glowing trails and burst into
coloured sparks, while confetti flutters down over the whole desktop. Fires on
the ``/celebrate`` command and (optionally) when a guided task completes. Pure
visuals — no AI, no network.
"""

from __future__ import annotations

import logging
import math
import random
import sys
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

from clicky.design_system import DS, hex_to_rgb
from clicky.effects.particles import Particle, spawn_burst, step_all
from clicky.ui.win32_transparency import apply_win32_transparency

logger = logging.getLogger(__name__)

_TICK_MS = 16
_DEFAULT_DURATION_MS = 4200.0    # how long new shells/confetti keep spawning


@dataclass
class _Shell:
    """A rising firework shell that bursts at its apex."""

    x: float
    y: float
    vy: float                      # negative = rising
    target_y: float
    color: tuple[int, int, int]
    trail_t: float = 0.0


@dataclass
class _Confetti:
    x: float
    y: float
    vx: float
    vy: float
    color: tuple[int, int, int]
    w: float
    h: float
    angle: float
    spin: float
    sway_phase: float
    sway_amp: float
    life: float
    max_life: float = field(default=0.0)

    def __post_init__(self) -> None:
        if self.max_life == 0.0:
            self.max_life = self.life


class CelebrationWidget(QWidget):
    """Fullscreen transparent overlay rendering fireworks + confetti."""

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
        self._shells: list[_Shell] = []
        self._sparks: list[Particle] = []
        self._confetti: list[_Confetti] = []

        self._spawn_remaining_ms = 0.0
        self._shell_cooldown_ms = 0.0
        self._confetti_cooldown_ms = 0.0
        self._intensity = 1.0

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def celebrate(self, duration_ms: float = _DEFAULT_DURATION_MS, intensity: float = 1.0) -> None:
        """Start (or extend) a celebration burst."""
        virtual = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(virtual)
        self._intensity = max(0.3, min(2.0, intensity))
        self._spawn_remaining_ms = max(self._spawn_remaining_ms, duration_ms)
        self.show()
        if not self._timer.isActive():
            self._timer.start()
        # Immediate opening volley so it pops the instant it's triggered.
        for _ in range(int(3 * self._intensity)):
            self._launch_shell()
        self._spawn_confetti_row(int(28 * self._intensity))

    def stop(self) -> None:
        self._timer.stop()
        self._shells.clear()
        self._sparks.clear()
        self._confetti.clear()
        self.hide()

    # ------------------------------------------------------------------
    # Spawning
    # ------------------------------------------------------------------

    def _launch_shell(self) -> None:
        w = max(1, self.width())
        h = max(1, self.height())
        x = self._rng.uniform(w * 0.12, w * 0.88)
        target_y = self._rng.uniform(h * 0.12, h * 0.42)
        start_y = h + 10
        rise_dist = start_y - target_y
        # v² = 2·g·d → initial speed that just reaches the apex under gravity.
        gravity = 900.0
        vy = -math.sqrt(2.0 * gravity * rise_dist)
        color = hex_to_rgb(self._rng.choice(DS.FIREWORK_PALETTE))
        self._shells.append(_Shell(x=x, y=start_y, vy=vy, target_y=target_y, color=color))

    def _burst_shell(self, shell: _Shell) -> None:
        count = int(self._rng.randint(48, 80) * self._intensity)
        self._sparks.extend(
            spawn_burst(
                shell.x, shell.y, count, DS.FIREWORK_PALETTE,
                speed=self._rng.uniform(300.0, 480.0),
                speed_jitter=0.35,
                life=1.3,
                life_jitter=0.4,
                size=self._rng.uniform(2.6, 4.2),
                gravity=240.0,
                drag=0.55,
                rng=self._rng,
            )
        )
        # A bright matching core flash.
        shell_hex = "#{:02x}{:02x}{:02x}".format(*shell.color)
        self._sparks.extend(
            spawn_burst(
                shell.x, shell.y, int(count * 0.4), ["#ffffff", shell_hex],
                speed=self._rng.uniform(150.0, 260.0),
                life=0.7, gravity=200.0, drag=0.4, size=2.2, rng=self._rng,
            )
        )

    def _spawn_confetti_row(self, n: int) -> None:
        w = max(1, self.width())
        for _ in range(n):
            x = self._rng.uniform(0, w)
            color = hex_to_rgb(self._rng.choice(DS.CONFETTI_PALETTE))
            self._confetti.append(_Confetti(
                x=x, y=self._rng.uniform(-40, -4),
                vx=self._rng.uniform(-30, 30),
                vy=self._rng.uniform(90, 190),
                color=color,
                w=self._rng.uniform(7, 13),
                h=self._rng.uniform(10, 18),
                angle=self._rng.uniform(0, math.pi * 2),
                spin=self._rng.uniform(-6, 6),
                sway_phase=self._rng.uniform(0, math.pi * 2),
                sway_amp=self._rng.uniform(20, 60),
                life=self._rng.uniform(3.0, 5.0),
            ))

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        dt = _TICK_MS / 1000.0
        h = max(1, self.height())

        if self._spawn_remaining_ms > 0:
            self._spawn_remaining_ms -= _TICK_MS
            self._shell_cooldown_ms -= _TICK_MS
            self._confetti_cooldown_ms -= _TICK_MS
            if self._shell_cooldown_ms <= 0:
                self._launch_shell()
                self._shell_cooldown_ms = self._rng.uniform(220, 480) / self._intensity
            if self._confetti_cooldown_ms <= 0:
                self._spawn_confetti_row(int(10 * self._intensity))
                self._confetti_cooldown_ms = 260

        # Shells.
        gravity = 900.0
        still_rising: list[_Shell] = []
        for s in self._shells:
            s.vy += gravity * dt
            s.y += s.vy * dt
            s.trail_t += dt
            # Burst at apex (velocity turns downward) or when reaching target.
            if s.vy >= -20.0 or s.y <= s.target_y:
                self._burst_shell(s)
            else:
                still_rising.append(s)
        self._shells = still_rising

        # Sparks.
        self._sparks = step_all(self._sparks, dt)

        # Confetti.
        alive: list[_Confetti] = []
        for c in self._confetti:
            c.life -= dt
            c.sway_phase += dt * 3.0
            c.x += (c.vx + math.sin(c.sway_phase) * c.sway_amp) * dt
            c.y += c.vy * dt
            c.angle += c.spin * dt
            if c.life > 0 and c.y < h + 30:
                alive.append(c)
        self._confetti = alive

        if (
            self._spawn_remaining_ms <= 0
            and not self._shells
            and not self._sparks
            and not self._confetti
        ):
            self.stop()
            return

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

        # Confetti first (behind the sparks).
        self._paint_confetti(painter)

        # Rising shell heads with a small glowing trail.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setPen(Qt.PenStyle.NoPen)
        for s in self._shells:
            r, g, b = s.color
            grad = QRadialGradient(QPointF(s.x, s.y), 9)
            grad.setColorAt(0.0, QColor(255, 255, 255, 230))
            grad.setColorAt(0.5, QColor(r, g, b, 180))
            grad.setColorAt(1.0, QColor(r, g, b, 0))
            painter.setBrush(grad)
            painter.drawEllipse(QPointF(s.x, s.y), 9, 9)

        # Sparks (additive glow).
        for p in self._sparks:
            a = p.alpha
            if a <= 0.02:
                continue
            r, g, b = p.color
            halo = p.size * 2.6
            grad = QRadialGradient(QPointF(p.x, p.y), halo)
            grad.setColorAt(0.0, QColor(r, g, b, int(170 * a)))
            grad.setColorAt(1.0, QColor(r, g, b, 0))
            painter.setBrush(grad)
            painter.drawEllipse(QPointF(p.x, p.y), halo, halo)
            painter.setBrush(QColor(
                min(255, r + 70), min(255, g + 70), min(255, b + 70), int(235 * a)
            ))
            painter.drawEllipse(QPointF(p.x, p.y), max(0.6, p.size * 0.7), max(0.6, p.size * 0.7))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.end()

    def _paint_confetti(self, painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        for c in self._confetti:
            r, g, b = c.color
            fade = min(1.0, c.life / 1.0)
            painter.save()
            painter.translate(c.x, c.y)
            painter.rotate(math.degrees(c.angle))
            # Foreshorten the flake as it spins for a 3D flutter feel.
            squish = abs(math.cos(c.sway_phase * 1.3))
            painter.setBrush(QColor(r, g, b, int(235 * fade)))
            painter.drawRoundedRect(
                QRectF(-c.w / 2, -c.h / 2 * squish, c.w, max(1.0, c.h * squish)), 2, 2
            )
            painter.restore()
