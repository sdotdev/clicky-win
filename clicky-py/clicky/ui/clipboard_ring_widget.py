"""Clipboard Ring — radial spinning HUD of clipboard history.

Stores up to 10 recent clipboard items and shows them in a glowing ring HUD.
Navigate with arrow keys; press Enter/Space to paste. Auto-hides after
3 s of inactivity. Activated with /clipboard.
"""

from __future__ import annotations

import math
import sys
import time
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

from clicky.design_system import DS, ease_out_back, hex_to_rgb
from clicky.ui.win32_transparency import apply_win32_transparency

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_ITEMS = 10
_RING_RADIUS = 220.0          # distance from center to item chips
_RING_INNER = 90.0            # inner dark glass circle radius
_ITEM_CHIP_W = 180.0
_ITEM_CHIP_H = 38.0
_AUTO_HIDE_MS = 3500          # hide after 3.5s of no input
_SPIN_DURATION_MS = 220.0     # rotation animation duration
_ENTER_DURATION_MS = 340.0    # enter animation (chips fly in from center)


class ClipboardRingWidget(QWidget):
    """Fullscreen interactive HUD showing recent clipboard history in a ring."""

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
        # NOTE: WA_TransparentForMouseEvents is intentionally NOT set —
        # this widget must receive key events.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("background:transparent;")

        # --- State ---------------------------------------------------------
        self._items: list[str] = []       # clipboard history, newest first
        self._selected: int = 0           # currently highlighted item index
        self._visible: bool = False
        self._enter_t: float = 0.0        # 0→1 during enter animation
        self._spin_t: float = 0.0         # 0→1 during spin animation
        self._spin_delta: int = 0         # +1 or -1 direction
        self._angle_offset: float = 0.0   # current rotation angle (radians)
        self._target_angle: float = 0.0   # target after spin
        self._inactivity_ms: float = 0.0  # counts up, resets on key press
        self._fade_alpha: float = 0.0     # 0→1 on show

        # --- Timer ---------------------------------------------------------
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

        # --- Clipboard watcher ---------------------------------------------
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

        # --- Geometry: fullscreen on primary screen ------------------------
        virtual = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(virtual)

    # ------------------------------------------------------------------
    # Clipboard watcher
    # ------------------------------------------------------------------

    def _on_clipboard_changed(self) -> None:
        text = QApplication.clipboard().text()
        if text and (not self._items or text != self._items[0]):
            self._items.insert(0, text)
            self._items = self._items[:_MAX_ITEMS]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_ring(self) -> None:
        """Show the ring HUD. No-ops if there is nothing in clipboard history."""
        if not self._items:
            return
        virtual = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(virtual)
        self._visible = True
        self._enter_t = 0.0
        self._fade_alpha = 0.0
        self._inactivity_ms = 0.0
        self._selected = 0
        self._angle_offset = 0.0
        self._target_angle = 0.0
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self._timer.start()

    def hide_ring(self) -> None:
        """Begin fade-out; the timer will call hide() when alpha reaches 0."""
        self._visible = False

    # ------------------------------------------------------------------
    # Geometry helper
    # ------------------------------------------------------------------

    def _item_angle(self, i: int) -> float:
        n = len(self._items)
        if n == 0:
            return 0.0
        base = 2 * math.pi / n
        return base * i + self._angle_offset - math.pi / 2  # start from top

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    def _rotate(self, direction: int) -> None:
        n = len(self._items)
        if n == 0:
            return
        self._selected = (self._selected - direction) % n
        slot_angle = 2 * math.pi / n
        self._target_angle += direction * slot_angle

    # ------------------------------------------------------------------
    # Paste
    # ------------------------------------------------------------------

    def _paste_selected(self) -> None:
        if not self._items:
            return
        text = self._items[self._selected]
        QApplication.clipboard().setText(text)
        self.hide_ring()
        # Simulate Ctrl+V using pynput (best-effort)
        try:
            from pynput.keyboard import Controller, Key
            kb = Controller()
            time.sleep(0.05)
            with kb.pressed(Key.ctrl):
                kb.press('v')
                kb.release('v')
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Simulation tick
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        dt_ms = 16.0

        # Fade
        target_alpha = 1.0 if self._visible else 0.0
        self._fade_alpha += (target_alpha - self._fade_alpha) * 0.18

        if not self._visible and self._fade_alpha < 0.01:
            self._fade_alpha = 0.0
            self._timer.stop()
            self.hide()
            return

        # Enter animation
        if self._visible and self._enter_t < 1.0:
            self._enter_t = min(1.0, self._enter_t + dt_ms / _ENTER_DURATION_MS)

        # Spin animation: smooth lerp angle_offset toward target
        diff = self._target_angle - self._angle_offset
        self._angle_offset += diff * 0.22

        # Inactivity timer
        if self._visible:
            self._inactivity_ms += dt_ms
            if self._inactivity_ms >= _AUTO_HIDE_MS:
                self.hide_ring()

        self.update()

    # ------------------------------------------------------------------
    # Key events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._rotate(-1)
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._rotate(1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._paste_selected()
        elif key == Qt.Key.Key_Escape:
            self.hide_ring()
        self._inactivity_ms = 0.0
        event.accept()

    # ------------------------------------------------------------------
    # Win32 transparency
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: ARG002, N802
        if sys.platform == "win32":
            apply_win32_transparency(int(self.winId()))

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        if self._fade_alpha < 0.01:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        ga = self._fade_alpha
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        n = len(self._items)
        if n == 0:
            painter.end()
            return

        # ----------------------------------------------------------------
        # Background: large dark radial scrim centered on the ring
        # ----------------------------------------------------------------
        scrim_r = _RING_RADIUS + 120.0
        scrim_grad = QRadialGradient(QPointF(cx, cy), scrim_r)
        scrim_grad.setColorAt(0.0, QColor(10, 12, 20, int(200 * ga)))
        scrim_grad.setColorAt(0.7, QColor(10, 12, 20, int(160 * ga)))
        scrim_grad.setColorAt(1.0, QColor(10, 12, 20, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(scrim_grad)
        painter.drawEllipse(QPointF(cx, cy), scrim_r, scrim_r)

        # ----------------------------------------------------------------
        # Ring guide circle (faint dashed)
        # ----------------------------------------------------------------
        cr2, cg2, cb2 = hex_to_rgb(DS.Colors.neon_cyan)
        ring_pen = QPen(QColor(cr2, cg2, cb2, int(30 * ga)))
        ring_pen.setWidthF(1.0)
        ring_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), _RING_RADIUS, _RING_RADIUS)

        # ----------------------------------------------------------------
        # Item chips around the ring
        # ----------------------------------------------------------------
        for i, item in enumerate(self._items):
            angle = self._item_angle(i)

            # Enter animation: chips fly in from center
            t = self._enter_t
            ease = ease_out_back(max(0.001, t))
            dist = _RING_RADIUS * ease

            ix = cx + math.cos(angle) * dist
            iy = cy + math.sin(angle) * dist

            is_selected = (i == self._selected)

            # Scale up selected item
            scale = 1.28 if is_selected else 1.0
            cw = _ITEM_CHIP_W * scale
            ch = _ITEM_CHIP_H * scale

            if is_selected:
                # Glow halo behind selected chip
                glow = QRadialGradient(QPointF(ix, iy), 80.0)
                glow.setColorAt(0.0, QColor(cr2, cg2, cb2, int(80 * ga)))
                glow.setColorAt(1.0, QColor(cr2, cg2, cb2, 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_Plus
                )
                painter.setBrush(glow)
                painter.drawEllipse(QPointF(ix, iy), 80.0, 80.0)
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_SourceOver
                )

                chip_color = QColor(cr2, cg2, cb2, int(220 * ga))
                text_color = QColor(8, 10, 18, int(255 * ga))
            else:
                chip_color = QColor(30, 35, 55, int(200 * ga))
                text_color = QColor(180, 190, 220, int(200 * ga))

            # Chip body
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(chip_color)
            painter.drawRoundedRect(
                QRectF(ix - cw / 2, iy - ch / 2, cw, ch),
                _ITEM_CHIP_H / 2 * scale,
                _ITEM_CHIP_H / 2 * scale,
            )

            # Chip text (truncated)
            label = item.strip().replace('\n', ' ')
            if len(label) > 22:
                label = label[:20] + "…"

            font_size = 10 if is_selected else 9
            font = QFont("Consolas", font_size)
            if is_selected:
                font.setWeight(QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(text_color)
            painter.drawText(
                QRectF(ix - cw / 2 + 8, iy - ch / 2, cw - 16, ch),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                label,
            )

        # ----------------------------------------------------------------
        # Inner glass hub
        # ----------------------------------------------------------------
        hub_grad = QRadialGradient(QPointF(cx, cy), _RING_INNER)
        hub_grad.setColorAt(0.0, QColor(18, 20, 32, int(240 * ga)))
        hub_grad.setColorAt(1.0, QColor(12, 14, 24, int(220 * ga)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(hub_grad)
        painter.drawEllipse(QPointF(cx, cy), _RING_INNER, _RING_INNER)

        # Hub border ring
        hub_pen = QPen(QColor(cr2, cg2, cb2, int(100 * ga)))
        hub_pen.setWidthF(1.5)
        painter.setPen(hub_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), _RING_INNER, _RING_INNER)

        # Hub content: selected item preview
        if self._items:
            selected_text = self._items[self._selected].strip().replace('\n', ' ')
            if len(selected_text) > 40:
                selected_text = selected_text[:38] + "…"

            # "CLIPBOARD" title label
            title_font = QFont("Consolas", 9, QFont.Weight.Bold)
            title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
            painter.setFont(title_font)
            painter.setPen(QColor(cr2, cg2, cb2, int(200 * ga)))
            painter.drawText(
                QRectF(cx - _RING_INNER + 10, cy - 30, _RING_INNER * 2 - 20, 20),
                Qt.AlignmentFlag.AlignCenter,
                "CLIPBOARD",
            )

            # Preview text
            preview_font = QFont("Segoe UI", 9)
            painter.setFont(preview_font)
            painter.setPen(QColor(220, 225, 240, int(210 * ga)))
            painter.drawText(
                QRectF(cx - _RING_INNER + 10, cy - 8, _RING_INNER * 2 - 20, 40),
                Qt.AlignmentFlag.AlignHCenter
                | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap,
                selected_text,
            )

            # Navigation hint
            hint_font = QFont("Consolas", 8)
            painter.setFont(hint_font)
            painter.setPen(QColor(100, 110, 140, int(150 * ga)))
            painter.drawText(
                QRectF(cx - _RING_INNER + 10, cy + 38, _RING_INNER * 2 - 20, 20),
                Qt.AlignmentFlag.AlignCenter,
                "← → ENTER",
            )

        painter.end()
