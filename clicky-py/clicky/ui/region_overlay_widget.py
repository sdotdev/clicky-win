"""Full-screen dimming overlay for REGION step mode.

Covers all monitors with a semi-transparent dark overlay, animates an orange
dashed rectangle growing from the top-left corner to the target region, then
punches a transparent "spotlight" hole so the highlighted area shows clearly.
Emits region_entered after a 5-second arm delay once the user's cursor moves
inside the rectangle.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)

_OVERLAY_ALPHA = 160       # 0-255 darkness of surrounding area
_BORDER_COLOR = "#FF6B00"  # orange
_BORDER_WIDTH = 2
_ARM_DELAY_MS = 5000       # wait 5 s before detecting mouse entry
_ANIM_DURATION_MS = 380
_MARCH_INTERVAL_MS = 60    # dashes animate offset every N ms


class RegionOverlayWidget(QWidget):
    """Fullscreen semi-transparent overlay with an animated highlighted region."""

    region_entered = Signal()

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

        self._target: QRectF = QRectF()  # final target region in widget-local coords
        self._target_global: QRectF = QRectF() # final target region in global coords
        self._progress: float = 0.0      # 0→1 animation progress
        self._dash_offset: float = 0.0

        self._anim = QPropertyAnimation(self, b"anim_progress")
        self._anim.setDuration(_ANIM_DURATION_MS)
        self.setProperty("anim_progress", 0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Marching ants timer (runs while overlay is visible)
        self._march_timer = QTimer(self)
        self._march_timer.setInterval(_MARCH_INTERVAL_MS)
        self._march_timer.timeout.connect(self._march_tick)

        # 5-second arm delay before we start checking for mouse entry
        self._arm_timer = QTimer(self)
        self._arm_timer.setSingleShot(True)
        self._arm_timer.setInterval(_ARM_DELAY_MS)
        self._arm_timer.timeout.connect(self._arm)
        self._armed = False

        # Cursor poll timer
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(100)
        self._cursor_timer.timeout.connect(self._check_cursor)

    # ------------------------------------------------------------------
    # Qt property for animation
    # ------------------------------------------------------------------

    def _get_progress(self) -> float:
        return self._progress

    def _set_progress(self, val: float) -> None:
        self._progress = val
        self.update()

    anim_progress = Property(float, _get_progress, _set_progress)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_region(self, x1: int, y1: int, x2: int, y2: int, label: str = "") -> None:
        """Show the overlay and animate the dashed region from (x1,y1) to (x2,y2)."""
        self._armed = False
        self._arm_timer.stop()
        self._cursor_timer.stop()

        # Cover the full virtual desktop.
        virtual = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(virtual)

        # Store the target in widget-local coords (offset by virtual desktop origin).
        local_x1 = x1 - virtual.x()
        local_y1 = y1 - virtual.y()
        local_x2 = x2 - virtual.x()
        local_y2 = y2 - virtual.y()
        
        self._target = QRectF(
            min(local_x1, local_x2), min(local_y1, local_y2),
            abs(x2 - x1), abs(y2 - y1),
        )
        self._target_global = QRectF(
            min(x1, x2), min(y1, y2),
            abs(x2 - x1), abs(y2 - y1),
        )
        self._progress = 0.0
        self.show()

        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._march_timer.start()

        # Start the 5-second arm delay.
        self._arm_timer.start()
        logger.info("region overlay shown: (%d,%d)→(%d,%d) label=%s", x1, y1, x2, y2, label)

    def hide_overlay(self) -> None:
        """Stop timers and hide."""
        self._anim.stop()
        self._march_timer.stop()
        self._arm_timer.stop()
        self._cursor_timer.stop()
        self._armed = False
        self.hide()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _arm(self) -> None:
        self._armed = True
        self._cursor_timer.start()

    def _march_tick(self) -> None:
        self._dash_offset = (self._dash_offset + 1.0) % 20.0
        self.update()

    def _check_cursor(self) -> None:
        if not self._armed:
            return
        from PySide6.QtGui import QCursor
        pos = QCursor.pos()
        if self._target_global.contains(float(pos.x()), float(pos.y())):
            self._cursor_timer.stop()
            self.hide_overlay()
            self.region_entered.emit()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: ARG002
        if self._target.isEmpty():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Animated draw rect (grows from top-left corner to full size).
        t = self._progress
        draw_rect = QRectF(
            self._target.x(),
            self._target.y(),
            self._target.width() * t,
            self._target.height() * t,
        )

        # 1. Semi-transparent dark overlay over entire widget.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, _OVERLAY_ALPHA))
        painter.drawRect(self.rect())

        if not draw_rect.isEmpty():
            # 2. Punch a transparent hole for the highlighted region.
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.drawRect(draw_rect)

            # 3. Draw marching-ants dashed border around the region.
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor(_BORDER_COLOR))
            pen.setWidthF(_BORDER_WIDTH)
            pen.setStyle(Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([6, 4])
            pen.setDashOffset(self._dash_offset)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(draw_rect)

        painter.end()
