"""Mouse shake detector — emits shake_detected when rapid directional reversals are observed."""

from __future__ import annotations
import time
from collections import deque
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QCursor


class ShakeDetector(QObject):
    shake_detected = Signal()

    POLL_INTERVAL_MS = 33        # ~30fps
    WINDOW_MS = 500              # rolling window to count reversals in
    MIN_TRAVEL_PX = 40           # min pixels per reversal to count
    DEBOUNCE_MS = 800            # ignore further shakes after detection

    def __init__(self, sensitivity: float = 0.5, parent=None):
        super().__init__(parent)
        self._sensitivity = sensitivity
        self._required = max(3, round(6 - sensitivity * 3))
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._prev_x = 0
        self._prev_y = 0
        self._vx = 0.0
        self._vy = 0.0
        self._reversals: deque[float] = deque()
        self._debounce_until: float = 0.0
        self._started = False

    def set_sensitivity(self, s: float) -> None:
        self._sensitivity = max(0.0, min(1.0, s))
        self._required = max(3, round(6 - self._sensitivity * 3))

    def start(self) -> None:
        if not self._started:
            pos = QCursor.pos()
            self._prev_x = pos.x()
            self._prev_y = pos.y()
            self._started = True
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._started = False
        self._reversals.clear()

    def _poll(self) -> None:
        pos = QCursor.pos()
        cx, cy = pos.x(), pos.y()
        dx = cx - self._prev_x
        dy = cy - self._prev_y
        now = time.monotonic()

        # Prune old reversals outside the window
        cutoff = now - self.WINDOW_MS / 1000.0
        while self._reversals and self._reversals[0] < cutoff:
            self._reversals.popleft()

        # Detect X-axis reversal (sign change with sufficient travel)
        if dx != 0:
            new_vx = 1 if dx > 0 else -1
            if self._vx != 0 and new_vx != self._vx and abs(dx) >= self.MIN_TRAVEL_PX:
                self._reversals.append(now)
            if abs(dx) > 2:  # only update velocity direction if meaningful movement
                self._vx = new_vx

        # Detect Y-axis reversal
        if dy != 0:
            new_vy = 1 if dy > 0 else -1
            if self._vy != 0 and new_vy != self._vy and abs(dy) >= self.MIN_TRAVEL_PX:
                self._reversals.append(now)
            if abs(dy) > 2:
                self._vy = new_vy

        self._prev_x = cx
        self._prev_y = cy

        # Check if shake threshold met
        if now < self._debounce_until:
            return
        if len(self._reversals) >= self._required:
            self._reversals.clear()
            self._debounce_until = now + self.DEBOUNCE_MS / 1000.0
            self.shake_detected.emit()
