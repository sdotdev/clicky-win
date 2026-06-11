"""Focus Spotlight overlay — dims the screen except for a glowing spotlight window.

Dims the entire desktop with a dark veil and cuts a soft spotlight over the
active region. On Windows the spotlight tracks the foreground window; on other
platforms it defaults to a cursor-following circle.  Activated with /focus.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget

from clicky.ui.win32_transparency import apply_win32_transparency


class FocusOverlayWidget(QWidget):
    """Fullscreen transparent overlay that dims all but a spotlight region."""

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

        self._spotlight_rect: QRectF | None = None
        self._target_rect: QRectF | None = None
        self._enabled: bool = False
        self._dim_alpha: float = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps
        self._timer.timeout.connect(self._tick)

        self._update_timer = QTimer(self)
        self._update_timer.setInterval(500)
        self._update_timer.timeout.connect(self._update_spotlight)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

    def set_spotlight_rect(self, rect: QRectF) -> None:
        """Manually set the spotlight (for testing/demo)."""
        self._target_rect = rect

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def _enable(self) -> None:
        self._enabled = True
        virtual = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(virtual)
        self._target_rect = self._query_active_window()
        if self._spotlight_rect is None:
            self._spotlight_rect = self._target_rect
        self.show()
        self._timer.start()
        self._update_timer.start()

    def _disable(self) -> None:
        self._enabled = False
        self._update_timer.stop()
        # _dim_alpha fades to 0 in _tick, then hides widget

    # ------------------------------------------------------------------
    # Active window query
    # ------------------------------------------------------------------

    def _query_active_window(self) -> QRectF | None:
        """Return the active window rect in widget-local coords. Win32 only."""
        if sys.platform != "win32":
            # Fallback: 700x500 rect centered on current cursor
            from PySide6.QtGui import QCursor
            cur = QCursor.pos()
            vg = QApplication.primaryScreen().virtualGeometry()
            cx = cur.x() - vg.x()
            cy = cur.y() - vg.y()
            return QRectF(cx - 350, cy - 250, 700, 500)
        try:
            import ctypes
            import ctypes.wintypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            # Skip own widget window
            own = int(self.winId()) if self.isVisible() else 0
            if hwnd == own:
                return self._spotlight_rect
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            vg = QApplication.primaryScreen().virtualGeometry()
            ox, oy = vg.x(), vg.y()
            x1 = rect.left - ox - 12   # slight padding
            y1 = rect.top - oy - 12
            x2 = rect.right - ox + 12
            y2 = rect.bottom - oy + 12
            w = max(100.0, float(x2 - x1))
            h = max(60.0, float(y2 - y1))
            return QRectF(float(x1), float(y1), w, h)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        dt = 33 / 1000.0

        # Animate dim alpha toward target
        target_alpha = 1.0 if self._enabled else 0.0
        if self._dim_alpha < target_alpha:
            self._dim_alpha = min(target_alpha, self._dim_alpha + dt * 3.5)
        elif self._dim_alpha > target_alpha:
            self._dim_alpha = max(target_alpha, self._dim_alpha - dt * 3.5)

        # When fully faded out, hide and stop timer
        if not self._enabled and self._dim_alpha < 0.01:
            self._dim_alpha = 0.0
            self._timer.stop()
            self.hide()
            return

        # Lerp spotlight rect toward target
        if self._target_rect is not None:
            if self._spotlight_rect is None:
                # Snap immediately
                self._spotlight_rect = self._target_rect
            else:
                f = 0.12
                sr = self._spotlight_rect
                tr = self._target_rect
                self._spotlight_rect = QRectF(
                    sr.x() + (tr.x() - sr.x()) * f,
                    sr.y() + (tr.y() - sr.y()) * f,
                    sr.width() + (tr.width() - sr.width()) * f,
                    sr.height() + (tr.height() - sr.height()) * f,
                )

        self.update()

    def _update_spotlight(self) -> None:
        result = self._query_active_window()
        if result is not None:
            self._target_rect = result

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: ARG002, N802
        if sys.platform == "win32":
            apply_win32_transparency(int(self.winId()))

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        if self._dim_alpha < 0.01:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        rect = self._spotlight_rect

        # --- Step 1: draw the dark veil using a temporary compositing image ---
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        ip = QPainter(img)
        ip.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fill with dark overlay
        dim = int(165 * self._dim_alpha)
        ip.fillRect(0, 0, w, h, QColor(0, 0, 0, dim))

        if rect is not None:
            # Punch a hole using CompositionMode_Source with transparent fill
            ip.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            # Feathered hole: gradient from transparent (center) to dark (edge)
            # Use 3 gradient stops to feather the edge
            pad = 40.0  # feather width
            cx = rect.x() + rect.width() / 2
            cy = rect.y() + rect.height() / 2
            # For rectangular spotlight, use linear gradients on each side
            # Simpler: use a soft rounded rect punch-out
            hole = QPainterPath()
            hole.addRoundedRect(rect, 16, 16)
            ip.setBrush(QColor(0, 0, 0, 0))  # fully transparent = punch hole
            ip.setPen(Qt.PenStyle.NoPen)
            ip.drawPath(hole)

            # Soft feather: draw gradient rings at the edge
            ip.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            # Draw a slightly-larger rounded rect with a gradient that fades from
            # opaque (outer) to transparent (inner = keep the hole)
            # Actually just skip complex feathering and use a simple linear border blend
            ip.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        ip.end()
        painter.drawImage(0, 0, img)

        # --- Step 2: accent border glow around the spotlight ---
        if rect is not None:
            alpha = self._dim_alpha
            # Outer glow (neon cyan)
            from clicky.design_system import hex_to_rgb
            from clicky.design_system import DS
            cr, cg, cb = hex_to_rgb(DS.Colors.neon_cyan)

            # Multi-pass glow: 3 passes with increasing width, decreasing alpha
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for width, glow_a in [(12.0, 20), (6.0, 45), (2.0, 140)]:
                pen = QPen(QColor(cr, cg, cb, int(glow_a * alpha)))
                pen.setWidthF(width)
                painter.setPen(pen)
                painter.drawRoundedRect(rect, 16, 16)

            # "FOCUS" label at top-left of spotlight
            font = QFont("Consolas", 9, QFont.Weight.Bold)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
            painter.setFont(font)
            painter.setPen(QColor(cr, cg, cb, int(180 * alpha)))
            painter.drawText(QPointF(rect.x() + 10, rect.y() - 8), "◈ FOCUS")

        painter.end()
