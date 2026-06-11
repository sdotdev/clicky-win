"""Swarm overlay — ghost companion triangles that orbit the cursor and flash arrows/regions."""
from __future__ import annotations

import asyncio
import logging
import math
import random
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

from clicky.design_system import DS, hex_to_rgb
from clicky.ui.win32_transparency import apply_win32_transparency

if TYPE_CHECKING:
    from clicky.commands.swarm_command import SwarmAction

logger = logging.getLogger(__name__)

_SPRING_K = 18.0
_DAMPING = 0.78
_TICK_MS = 16

_TRAIL_LEN = 3
_GHOST_TRI_SIZE = 21       # same as CompanionWidget.TRIANGLE_SIZE
_STAGGER_MS = 120

_ORBIT_RADIUS = 200
_REPOSITION_MIN_MS = 400   # per-agent interval drawn uniformly from this range
_REPOSITION_MAX_MS = 1200
_ARROW_FADE_MS = 700.0
_ARROW_CHANCE = 0.30
_REGION_GROW_MS = 280.0    # region box grow-in duration (matches DragBoxWidget)
_REGION_FADE_MS = 1200.0   # flash region lifetime
_REGION_CHANCE = 0.20      # probability of region box on each reposition
_REGION_SIZE = 80          # half-size of the flash region box (px)
_REGION_BORDER = "#FF6B00"
_MARCH_STEP = 1.2          # dash offset increment per tick

_PHASE_LAUNCH_MS = 300.0
_PHASE_ORBIT_MS = 9000.0
_PHASE_RECOMBINE_MS = 500.0


class _Phase(Enum):
    IDLE = auto()
    LAUNCH = auto()
    ORBIT = auto()
    RECOMBINE = auto()


@dataclass
class _FlashArrow:
    sx: float
    sy: float
    ex: float
    ey: float
    ctrl_x: float = 0.0   # quadratic bezier control point (perpendicular offset)
    ctrl_y: float = 0.0
    opacity: float = 1.0


@dataclass
class _FlashRegion:
    cx: float          # widget-local centre x
    cy: float          # widget-local centre y
    opacity: float = 1.0
    dash_offset: float = 0.0
    grow_t: float = 0.0    # 0→1 over _REGION_GROW_MS, OutCubic easing


@dataclass
class _Agent:
    pos: QPointF
    vel: QPointF
    target: QPointF
    action: "SwarmAction"
    opacity: float = 0.0
    angle: float = 0.0
    trail: list = field(default_factory=list)
    delay_ms: float = 0.0
    _active: bool = False
    _reposition_elapsed: float = 0.0
    _next_reposition_ms: float = 800.0   # drawn fresh each reposition
    _reposition_offset: float = 0.0      # initial stagger before first reposition


class SwarmOverlayWidget(QWidget):
    """Fullscreen transparent overlay — ghost triangles orbiting the cursor."""

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

        self._agents: list[_Agent] = []
        self._flash_arrows: list[_FlashArrow] = []
        self._flash_regions: list[_FlashRegion] = []
        self._phase = _Phase.IDLE
        self._phase_elapsed_ms: float = 0.0
        self._origin: QPointF = QPointF(0, 0)
        self._orbit_anchor: QPointF = QPointF(0, 0)
        self._fixed_anchor: bool = False
        self._commands_fired = False

        self.pending_actions: list[SwarmAction] = []
        self.pending_anchor: QPointF | None = None

        self._screenshot_scale_x: float = 1.0
        self._screenshot_scale_y: float = 1.0
        self._monitor_left: int = 0
        self._monitor_top: int = 0

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(_TICK_MS)
        self._tick_timer.timeout.connect(self._tick)

    def set_screen_info(
        self, scale_x: float, scale_y: float, monitor_left: int, monitor_top: int
    ) -> None:
        self._screenshot_scale_x = scale_x
        self._screenshot_scale_y = scale_y
        self._monitor_left = monitor_left
        self._monitor_top = monitor_top

    def set_pending_actions(self, actions: list[SwarmAction]) -> None:
        self.pending_actions = actions

    def start_swarm(self, origin: QPointF, actions: list[SwarmAction]) -> None:
        self._origin = origin
        self._agents = []
        self._flash_arrows = []
        self._flash_regions = []
        self._phase = _Phase.LAUNCH
        self._phase_elapsed_ms = 0.0
        self._commands_fired = False

        virtual = QApplication.primaryScreen().virtualGeometry()
        ox, oy = float(virtual.x()), float(virtual.y())
        lo = QPointF(origin.x() - ox, origin.y() - oy)

        if self.pending_anchor is not None:
            self._orbit_anchor = QPointF(
                self.pending_anchor.x() - ox, self.pending_anchor.y() - oy
            )
            self._fixed_anchor = True
        else:
            from PySide6.QtGui import QCursor
            cur = QCursor.pos()
            self._orbit_anchor = QPointF(cur.x() - ox, cur.y() - oy)
            self._fixed_anchor = False
        self.pending_anchor = None

        n = max(len(actions), 5)
        padded_actions: list[SwarmAction] = list(actions)
        from clicky.commands.swarm_command import SwarmAction as SA
        while len(padded_actions) < n:
            padded_actions.append(SA(x=0, y=0, cmd="", label=""))

        for i, action in enumerate(padded_actions):
            init_angle = i * (2 * math.pi / n) + random.uniform(-0.3, 0.3)
            init_target = QPointF(
                self._orbit_anchor.x() + math.cos(init_angle) * _ORBIT_RADIUS,
                self._orbit_anchor.y() + math.sin(init_angle) * _ORBIT_RADIUS,
            )
            agent = _Agent(
                pos=QPointF(lo),
                vel=QPointF(0.0, 0.0),
                target=QPointF(init_target),
                action=action,
                opacity=0.0,
                delay_ms=float(i * _STAGGER_MS),
                _next_reposition_ms=random.uniform(_REPOSITION_MIN_MS, _REPOSITION_MAX_MS),
                _reposition_offset=float(i * ((_REPOSITION_MIN_MS + _REPOSITION_MAX_MS) / 2 / n)),
            )
            agent._init_target = init_target  # type: ignore[attr-defined]
            palette_color = DS.POWER_PALETTE[i % len(DS.POWER_PALETTE)]
            agent._color_rgb = hex_to_rgb(palette_color)  # type: ignore[attr-defined]
            self._agents.append(agent)

        self.setGeometry(virtual)
        self.show()
        self._tick_timer.start()

    def showEvent(self, event) -> None:  # noqa: ARG002
        if sys.platform == "win32":
            apply_win32_transparency(int(self.winId()))

    # ------------------------------------------------------------------
    # Main tick
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        dt = _TICK_MS / 1000.0
        self._phase_elapsed_ms += _TICK_MS

        if not self._fixed_anchor and self._phase in (_Phase.LAUNCH, _Phase.ORBIT):
            virtual = QApplication.primaryScreen().virtualGeometry()
            from PySide6.QtGui import QCursor
            cur = QCursor.pos()
            self._orbit_anchor = QPointF(cur.x() - virtual.x(), cur.y() - virtual.y())

        if self._phase == _Phase.LAUNCH:
            self._tick_launch(dt)
            if self._phase_elapsed_ms >= _PHASE_LAUNCH_MS:
                self._enter_orbit()
        elif self._phase == _Phase.ORBIT:
            self._tick_orbit()
            if self._phase_elapsed_ms >= _PHASE_ORBIT_MS:
                self._enter_recombine()
        elif self._phase == _Phase.RECOMBINE:
            self._tick_recombine()
            if self._phase_elapsed_ms >= _PHASE_RECOMBINE_MS:
                self._finish()
                return

        # Age flash arrows
        next_arrows = []
        for a in self._flash_arrows:
            a.opacity -= _TICK_MS / _ARROW_FADE_MS
            if a.opacity > 0.0:
                next_arrows.append(a)
        self._flash_arrows = next_arrows

        # Age flash regions (grow in, march dashes, fade out)
        next_regions = []
        for r in self._flash_regions:
            r.opacity -= _TICK_MS / _REGION_FADE_MS
            r.dash_offset = (r.dash_offset + _MARCH_STEP) % 20.0
            r.grow_t = min(1.0, r.grow_t + _TICK_MS / _REGION_GROW_MS)
            if r.opacity > 0.0:
                next_regions.append(r)
        self._flash_regions = next_regions

        self._update_physics(dt)
        self.update()

    def _tick_launch(self, dt: float) -> None:
        t = self._phase_elapsed_ms
        for agent in self._agents:
            if t >= agent.delay_ms:
                if not agent._active:
                    agent._active = True
                    agent.target = agent._init_target  # type: ignore[attr-defined]
                agent.opacity = min(1.0, agent.opacity + dt * 5.0)

    def _enter_orbit(self) -> None:
        self._phase = _Phase.ORBIT
        self._phase_elapsed_ms = 0.0
        if not self._commands_fired:
            self._commands_fired = True
            for agent in self._agents:
                if agent.action.cmd:
                    asyncio.ensure_future(self._exec_cmd(agent.action.cmd, agent.action.label))

    def _tick_orbit(self) -> None:
        for agent in self._agents:
            if not agent._active:
                continue
            agent._reposition_elapsed += _TICK_MS
            threshold = agent._next_reposition_ms + agent._reposition_offset
            agent._reposition_offset = 0.0
            if agent._reposition_elapsed >= threshold:
                prev = QPointF(agent.pos)
                θ = random.uniform(0, 2 * math.pi)
                new_target = QPointF(
                    self._orbit_anchor.x() + math.cos(θ) * _ORBIT_RADIUS,
                    self._orbit_anchor.y() + math.sin(θ) * _ORBIT_RADIUS,
                )
                agent.target = new_target
                agent._reposition_elapsed = 0.0
                agent._next_reposition_ms = random.uniform(_REPOSITION_MIN_MS, _REPOSITION_MAX_MS)

                if random.random() < _ARROW_CHANCE:
                    # Control point: midpoint offset perpendicular to the line by ±80-200px
                    mx = (prev.x() + new_target.x()) * 0.5
                    my = (prev.y() + new_target.y()) * 0.5
                    adx = new_target.x() - prev.x()
                    ady = new_target.y() - prev.y()
                    alen = math.sqrt(adx * adx + ady * ady) or 1.0
                    perp_x, perp_y = -ady / alen, adx / alen
                    bend = random.choice([-1, 1]) * random.uniform(80, 200)
                    self._flash_arrows.append(_FlashArrow(
                        sx=prev.x(), sy=prev.y(),
                        ex=new_target.x(), ey=new_target.y(),
                        ctrl_x=mx + perp_x * bend,
                        ctrl_y=my + perp_y * bend,
                    ))
                if random.random() < _REGION_CHANCE:
                    self._flash_regions.append(_FlashRegion(
                        cx=new_target.x(), cy=new_target.y(),
                    ))

    def _enter_recombine(self) -> None:
        self._phase = _Phase.RECOMBINE
        self._phase_elapsed_ms = 0.0
        virtual = QApplication.primaryScreen().virtualGeometry()
        ox, oy = float(virtual.x()), float(virtual.y())
        lo = QPointF(self._origin.x() - ox, self._origin.y() - oy)
        for agent in self._agents:
            agent.target = QPointF(lo)

    def _tick_recombine(self) -> None:
        fade_start = _PHASE_RECOMBINE_MS - 200.0
        if self._phase_elapsed_ms >= fade_start:
            fade_t = (self._phase_elapsed_ms - fade_start) / 200.0
            for agent in self._agents:
                agent.opacity = max(0.0, 1.0 - fade_t)

    def _update_physics(self, dt: float) -> None:
        for agent in self._agents:
            if not agent._active:
                continue
            ax = (agent.target.x() - agent.pos.x()) * _SPRING_K
            ay = (agent.target.y() - agent.pos.y()) * _SPRING_K
            agent.vel = QPointF(
                (agent.vel.x() + ax * dt) * _DAMPING,
                (agent.vel.y() + ay * dt) * _DAMPING,
            )
            agent.pos = QPointF(
                agent.pos.x() + agent.vel.x() * dt,
                agent.pos.y() + agent.vel.y() * dt,
            )
            vx, vy = agent.vel.x(), agent.vel.y()
            if abs(vx) > 1.0 or abs(vy) > 1.0:
                agent.angle = math.atan2(vy, vx)
            agent.trail = (agent.trail + [QPointF(agent.pos)])[-_TRAIL_LEN:]

    def _finish(self) -> None:
        self._tick_timer.stop()
        self._agents.clear()
        self._flash_arrows.clear()
        self._flash_regions.clear()
        self._phase = _Phase.IDLE
        self.pending_actions.clear()
        self.hide()

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    _ALLOWED_VERBS = frozenset({
        "new-item", "move-item", "copy-item", "rename-item",
        "mkdir", "get-childitem", "get-item", "get-content",
        "set-content", "add-content", "clear-content",
        "compress-archive", "expand-archive",
        "sort-object", "where-object", "select-object",
        "write-output", "write-host",
    })

    _SHELL_METACHARACTERS = set(';|&`$\n\r')

    @classmethod
    def _cmd_is_allowed(cls, cmd: str) -> bool:
        if not cmd.strip():
            return False
        if any(c in cls._SHELL_METACHARACTERS for c in cmd):
            return False
        first = cmd.strip().split()[0].lower()
        if "\\" in first:
            first = first.split("\\")[-1]
        return first in cls._ALLOWED_VERBS

    async def _exec_cmd(self, cmd: str, label: str) -> None:
        if not self._cmd_is_allowed(cmd):
            logger.warning("swarm blocked disallowed command (%s): %s", label, cmd)
            return
        logger.info("swarm executing: %s", label)
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                timeout=30,
            )
            logger.info("swarm done: %s", label)
        except Exception as exc:  # noqa: BLE001
            logger.error("swarm action failed (%s): %s", label, exc)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: ARG002
        if not self._agents and not self._flash_arrows and not self._flash_regions:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent = QColor(DS.Colors.accent_blue)

        # Flash regions (no dimming — just dashed border)
        for region in self._flash_regions:
            self._paint_flash_region(painter, region)

        # Flash arrows
        for arrow in self._flash_arrows:
            self._paint_flash_arrow(painter, arrow, accent)

        # Orbit ring — faint dashed circle when agents are orbiting
        if self._phase == _Phase.ORBIT:
            ring_color = QColor(DS.Colors.neon_cyan)
            ring_color.setAlpha(35)
            ring_pen = QPen(ring_color)
            ring_pen.setWidthF(1.5)
            ring_pen.setStyle(Qt.PenStyle.CustomDashLine)
            ring_pen.setDashPattern([4, 8])
            painter.setPen(ring_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                self._orbit_anchor,
                float(_ORBIT_RADIUS),
                float(_ORBIT_RADIUS),
            )

        # Agents on top
        painter.setPen(Qt.PenStyle.NoPen)
        for agent in self._agents:
            if agent.opacity <= 0.01 or not agent._active:
                continue
            self._paint_agent(painter, agent, accent)

        painter.end()

    def _paint_flash_region(self, painter: QPainter, region: _FlashRegion) -> None:
        # OutCubic easing on grow_t so the box snaps open like DragBoxWidget
        t = region.grow_t
        ease = 1.0 - (1.0 - t) ** 3
        s = _REGION_SIZE * ease
        # Grow from top-left corner (same direction as DragBoxWidget)
        rect = QRectF(region.cx - _REGION_SIZE, region.cy - _REGION_SIZE, s * 2, s * 2)

        alpha = int(region.opacity * 200)
        color = QColor(_REGION_BORDER)
        color.setAlpha(alpha)

        # Very faint fill inside the dashed rect
        fill_color = QColor("#FF6B00")
        fill_color.setAlpha(int(region.opacity * 18))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill_color)
        painter.drawRect(rect)

        pen = QPen(color)
        pen.setWidthF(2.0)
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([6, 4])
        pen.setDashOffset(region.dash_offset)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

    def _paint_flash_arrow(self, painter: QPainter, arrow: _FlashArrow, accent: QColor) -> None:
        alpha = int(arrow.opacity * 200)
        color = QColor(accent)
        color.setAlpha(alpha)

        # Quadratic bezier stroke
        path = QPainterPath()
        path.moveTo(arrow.sx, arrow.sy)
        path.quadTo(arrow.ctrl_x, arrow.ctrl_y, arrow.ex, arrow.ey)

        # Glow pass — wide, low-alpha stroke
        glow_color = QColor(accent)
        glow_color.setAlpha(int(arrow.opacity * 60))
        glow_pen = QPen(glow_color)
        glow_pen.setWidthF(8.0)
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(glow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Crisp thin pass
        pen = QPen(color)
        pen.setWidthF(2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Arrowhead direction = tangent at end of quadratic bezier = end - control
        tdx = arrow.ex - arrow.ctrl_x
        tdy = arrow.ey - arrow.ctrl_y
        tlen = math.sqrt(tdx * tdx + tdy * tdy) or 1.0
        nx, ny = tdx / tlen, tdy / tlen
        px, py = -ny, nx
        head_size = 24.0
        head_wing = 12.0
        tip = QPointF(arrow.ex, arrow.ey)
        bx = arrow.ex - nx * head_size
        by = arrow.ey - ny * head_size
        w1 = QPointF(bx + px * head_wing, by + py * head_wing)
        w2 = QPointF(bx - px * head_wing, by - py * head_wing)

        # Glow pass arrowhead — slightly larger, low-alpha
        glow_head_color = QColor(accent)
        glow_head_color.setAlpha(int(arrow.opacity * 40))
        glow_scale = 1.35
        bxg = arrow.ex - nx * head_size * glow_scale
        byg = arrow.ey - ny * head_size * glow_scale
        wg1 = QPointF(bxg + px * head_wing * glow_scale, byg + py * head_wing * glow_scale)
        wg2 = QPointF(bxg - px * head_wing * glow_scale, byg - py * head_wing * glow_scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow_head_color)
        painter.drawPolygon(QPolygonF([tip, wg1, wg2]))

        # Crisp arrowhead
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([tip, w1, w2]))

    def _paint_agent(self, painter: QPainter, agent: _Agent, accent: QColor) -> None:
        a = int(agent.opacity * 220)

        # Per-agent color from palette (fall back to accent_blue if not set)
        color_rgb: tuple[int, int, int] = getattr(agent, "_color_rgb", None) or (
            accent.red(), accent.green(), accent.blue()
        )
        agent_color = QColor(color_rgb[0], color_rgb[1], color_rgb[2])

        cx, cy = agent.pos.x(), agent.pos.y()

        # Small trail dots (use agent color)
        for i, tp in enumerate(agent.trail):
            t = (i + 1) / max(len(agent.trail), 1)
            ta = int(t * agent.opacity * 70)
            tr = 0.5 + t * 1.5
            tc = QColor(agent_color)
            tc.setAlpha(ta)
            painter.setBrush(tc)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(tp, tr, tr)

        # Glow halo — QRadialGradient behind triangle
        halo_radius = _GHOST_TRI_SIZE * 2.2
        grad = QRadialGradient(cx, cy, halo_radius)
        halo_inner = QColor(color_rgb[0], color_rgb[1], color_rgb[2], int(90 * agent.opacity))
        halo_outer = QColor(color_rgb[0], color_rgb[1], color_rgb[2], 0)
        grad.setColorAt(0.0, halo_inner)
        grad.setColorAt(1.0, halo_outer)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), halo_radius, halo_radius)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Triangle — regular companion size, pointing in direction of travel
        h = _GHOST_TRI_SIZE
        w = h * 0.866

        tri_angle = agent.angle + math.pi
        tip_x = cx + w * 0.5 * math.cos(tri_angle)
        tip_y = cy + w * 0.5 * math.sin(tri_angle)
        b1a = tri_angle + math.radians(140)
        b2a = tri_angle - math.radians(140)
        b1x = cx + h * 0.4 * math.cos(b1a)
        b1y = cy + h * 0.4 * math.sin(b1a)
        b2x = cx + h * 0.4 * math.cos(b2a)
        b2y = cy + h * 0.4 * math.sin(b2a)

        tc = QColor(agent_color)
        tc.setAlpha(a)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tc)
        painter.drawPolygon(QPolygonF([
            QPointF(tip_x, tip_y),
            QPointF(b1x, b1y),
            QPointF(b2x, b2y),
        ]))

        # Action label chip — 20px above agent center, if label is non-empty
        label_text = agent.action.label
        if label_text:
            if len(label_text) > 14:
                label_text = label_text[:13] + "…"
            from PySide6.QtGui import QFont, QFontMetricsF
            chip_font = QFont("Consolas", 9)
            chip_font.setBold(True)
            painter.setFont(chip_font)
            fm = QFontMetricsF(chip_font)
            text_w = fm.horizontalAdvance(label_text)
            text_h = fm.height()
            pad_x, pad_y = 5.0, 3.0
            chip_w = text_w + pad_x * 2
            chip_h = text_h + pad_y * 2
            chip_x = cx - chip_w * 0.5
            chip_y = cy - 20 - chip_h
            chip_rect = QRectF(chip_x, chip_y, chip_w, chip_h)

            # Chip background using agent color, semi-transparent
            chip_bg = QColor(agent_color)
            chip_bg.setAlpha(int(agent.opacity * 200))
            painter.setBrush(chip_bg)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(chip_rect, 3, 3)

            # Dark text
            text_color = QColor("#0b0d12")
            text_color.setAlpha(int(agent.opacity * 230))
            painter.setPen(text_color)
            painter.drawText(chip_rect, Qt.AlignmentFlag.AlignCenter, label_text)
