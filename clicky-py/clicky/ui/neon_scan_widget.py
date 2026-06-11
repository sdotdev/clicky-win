"""Neon Scan HUD — a cyberpunk targeting sweep over the real desktop.

A glowing scan line sweeps down the screen; as it passes each detected UI
element, a neon bounding box "locks on" with animated corner brackets, a typed
label, and a pulse ring — like a sci-fi targeting computer. A HUD frame and
readout wrap the whole screen.

Boxes come from either the vision model (real mode) or :func:`demo_boxes`
(demo mode). This widget only renders — sourcing lives in
:mod:`clicky.effects.scan_layout` and the ``/scan`` command handler.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from clicky.design_system import DS, ease_out_back, hex_to_rgb
from clicky.effects.scan_layout import ScanBox
from clicky.ui.win32_transparency import apply_win32_transparency

logger = logging.getLogger(__name__)

_TICK_MS = 16
_SWEEP_MS = 1500.0          # time for the scan line to cross the screen
_BRACKET_MS = 260.0         # per-box corner-bracket lock-on animation
_HOLD_MS = 3200.0           # how long boxes stay after the sweep finishes
_FADE_MS = 650.0            # final fade-out


class _ScanState:
    SWEEP = "sweep"
    HOLD = "hold"
    FADE = "fade"
    IDLE = "idle"


class NeonScanWidget(QWidget):
    """Fullscreen transparent overlay rendering the neon targeting HUD."""

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

        self._boxes: list[ScanBox] = []
        self._activated: dict[int, float] = {}   # box index → elapsed at lock-on
        self._ox = 0
        self._oy = 0
        self._elapsed = 0.0
        self._state = _ScanState.IDLE
        self._fade_alpha = 1.0
        self._is_demo = True

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, boxes: list[ScanBox], *, demo: bool = True) -> None:
        """Begin a scan over ``boxes`` (already in screen coordinates)."""
        virtual = QApplication.primaryScreen().virtualGeometry()
        self._ox, self._oy = virtual.x(), virtual.y()
        self.setGeometry(virtual)
        # Convert to widget-local coordinates.
        self._boxes = [
            ScanBox(
                b.x1 - self._ox, b.y1 - self._oy,
                b.x2 - self._ox, b.y2 - self._oy,
                b.label, b.color_index,
            )
            for b in boxes
        ]
        self._activated = {}
        self._elapsed = 0.0
        self._fade_alpha = 1.0
        self._is_demo = demo
        self._state = _ScanState.SWEEP
        self.show()
        if not self._timer.isActive():
            self._timer.start()
        logger.info("Neon Scan started (%d boxes, demo=%s)", len(self._boxes), demo)

    def stop(self) -> None:
        self._timer.stop()
        self._boxes = []
        self._activated = {}
        self._state = _ScanState.IDLE
        self.hide()

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _box_color(self, box: ScanBox) -> tuple[int, int, int]:
        palette = DS.SCAN_PALETTE
        return hex_to_rgb(palette[box.color_index % len(palette)])

    def _sweep_y(self) -> float:
        h = max(1, self.height())
        t = min(1.0, self._elapsed / _SWEEP_MS)
        return t * (h + 40) - 20

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._elapsed += _TICK_MS

        if self._state == _ScanState.SWEEP:
            sweep_y = self._sweep_y()
            for i, box in enumerate(self._boxes):
                if i not in self._activated and box.cy <= sweep_y:
                    self._activated[i] = self._elapsed
            if self._elapsed >= _SWEEP_MS:
                # Make sure every box is locked on before holding.
                for i in range(len(self._boxes)):
                    self._activated.setdefault(i, self._elapsed)
                self._state = _ScanState.HOLD
                self._elapsed = 0.0
        elif self._state == _ScanState.HOLD:
            if self._elapsed >= _HOLD_MS:
                self._state = _ScanState.FADE
                self._elapsed = 0.0
        elif self._state == _ScanState.FADE:
            self._fade_alpha = max(0.0, 1.0 - self._elapsed / _FADE_MS)
            if self._elapsed >= _FADE_MS:
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
        if self._state == _ScanState.IDLE:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        ga = self._fade_alpha  # global alpha for fade-out

        self._paint_screen_frame(painter, ga)
        if self._state == _ScanState.SWEEP:
            self._paint_sweep(painter, ga)
        for i, box in enumerate(self._boxes):
            if i in self._activated:
                self._paint_box(painter, box, self._activated[i], ga)
        self._paint_readout(painter, ga)
        painter.end()

    # -- HUD chrome ----------------------------------------------------

    def _paint_screen_frame(self, painter: QPainter, ga: float) -> None:
        w, h = self.width(), self.height()
        cyan = hex_to_rgb(DS.Colors.neon_cyan)
        pen = QPen(QColor(cyan[0], cyan[1], cyan[2], int(120 * ga)))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        L = 46  # corner bracket arm length
        m = 18  # margin from edge
        corners = [
            (m, m, 1, 1), (w - m, m, -1, 1),
            (m, h - m, 1, -1), (w - m, h - m, -1, -1),
        ]
        for cx, cy, sx, sy in corners:
            painter.drawLine(int(cx), int(cy), int(cx + L * sx), int(cy))
            painter.drawLine(int(cx), int(cy), int(cx), int(cy + L * sy))

    def _paint_sweep(self, painter: QPainter, ga: float) -> None:
        w = self.width()
        y = self._sweep_y()
        cyan = hex_to_rgb(DS.Colors.neon_cyan)

        # Trailing glow gradient above the line.
        trail_h = 130.0
        grad = QLinearGradient(0, y - trail_h, 0, y)
        grad.setColorAt(0.0, QColor(cyan[0], cyan[1], cyan[2], 0))
        grad.setColorAt(1.0, QColor(cyan[0], cyan[1], cyan[2], int(55 * ga)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawRect(QRectF(0, y - trail_h, w, trail_h))

        # The bright scan line itself.
        line = QPen(QColor(255, 255, 255, int(230 * ga)))
        line.setWidthF(2.4)
        painter.setPen(line)
        painter.drawLine(QPointF(0, y), QPointF(w, y))
        glow = QPen(QColor(cyan[0], cyan[1], cyan[2], int(160 * ga)))
        glow.setWidthF(6.0)
        painter.setPen(glow)
        painter.drawLine(QPointF(0, y), QPointF(w, y))

        # Faint moving tick marks along the line for a scanner feel.
        tick = QPen(QColor(cyan[0], cyan[1], cyan[2], int(110 * ga)))
        tick.setWidthF(2.0)
        painter.setPen(tick)
        spacing = 80
        for x in range(0, w, spacing):
            painter.drawLine(QPointF(x, y - 6), QPointF(x, y + 6))

    def _paint_box(self, painter: QPainter, box: ScanBox, activated_at: float, ga: float) -> None:
        r, g, b = self._box_color(box)
        # Lock-on bracket animation 0..1.
        if self._state == _ScanState.SWEEP:
            t = min(1.0, (self._elapsed - activated_at) / _BRACKET_MS)
        else:
            t = 1.0
        ease = ease_out_back(max(0.001, t))

        x1, y1, x2, y2 = box.x1, box.y1, box.x2, box.y2
        bw, bh = x2 - x1, y2 - y1

        # Faint fill once locked.
        fill_a = int(26 * t * ga)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(r, g, b, fill_a))
        painter.drawRoundedRect(QRectF(x1, y1, bw, bh), 4, 4)

        # Thin full outline fades in.
        outline = QPen(QColor(r, g, b, int(120 * t * ga)))
        outline.setWidthF(1.4)
        painter.setPen(outline)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(x1, y1, bw, bh), 4, 4)

        # Bright animated corner brackets.
        arm = min(bw, bh) * 0.32 * ease
        bracket = QPen(QColor(255, 255, 255, int(235 * t * ga)))
        bracket.setWidthF(2.6)
        bracket.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bracket)
        for cx, cy, sx, sy in (
            (x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1),
        ):
            painter.drawLine(QPointF(cx, cy), QPointF(cx + arm * sx, cy))
            painter.drawLine(QPointF(cx, cy), QPointF(cx, cy + arm * sy))

        if t < 0.45:
            return

        # Pulse ring just after lock-on.
        if self._state == _ScanState.SWEEP and t < 1.0:
            pr = (1.0 - t) * 30.0
            ring = QPen(QColor(r, g, b, int(180 * (1.0 - t) * ga)))
            ring.setWidthF(2.0)
            painter.setPen(ring)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                QRectF(x1 - pr, y1 - pr, bw + pr * 2, bh + pr * 2), 6, 6
            )

        # Typed label chip.
        label = box.label.upper().replace("_", " ")
        shown = label
        if self._state == _ScanState.SWEEP:
            chars = max(1, int(len(label) * min(1.0, (t - 0.45) / 0.55)))
            shown = label[:chars]
        font = QFont("Consolas", 10, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_w = metrics.horizontalAdvance(shown)
        chip_w = text_w + 16
        chip_h = 20
        chip_x = x1
        chip_y = max(0, y1 - chip_h - 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(r, g, b, int(210 * ga)))
        painter.drawRoundedRect(QRectF(chip_x, chip_y, chip_w, chip_h), 3, 3)
        painter.setPen(QColor(8, 10, 16, int(255 * ga)))
        painter.drawText(
            QRectF(chip_x + 8, chip_y, chip_w, chip_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, shown,
        )

    def _paint_readout(self, painter: QPainter, ga: float) -> None:
        cyan = hex_to_rgb(DS.Colors.neon_cyan)
        lime = hex_to_rgb(DS.Colors.neon_lime)

        title_font = QFont("Consolas", 14, QFont.Weight.Bold)
        title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.0)
        painter.setFont(title_font)
        painter.setPen(QColor(cyan[0], cyan[1], cyan[2], int(235 * ga)))
        painter.drawText(QPointF(34, 50), "◢ NEON SCAN")

        sub_font = QFont("Consolas", 10, QFont.Weight.Bold)
        sub_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        painter.setFont(sub_font)
        if self._state == _ScanState.SWEEP:
            blink = "█" if int(self._elapsed / 250) % 2 == 0 else " "
            msg = f"SCANNING SURFACE… {len(self._activated)} LOCKED {blink}"
            painter.setPen(QColor(cyan[0], cyan[1], cyan[2], int(200 * ga)))
        else:
            mode = "DEMO" if self._is_demo else "LIVE"
            msg = f"{len(self._boxes)} TARGETS ACQUIRED · {mode} FEED"
            painter.setPen(QColor(lime[0], lime[1], lime[2], int(220 * ga)))
        painter.drawText(QPointF(34, 70), msg)
