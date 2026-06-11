"""Streaming text output panel — slides open when AI responds."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import QPlainTextEdit, QProgressBar, QVBoxLayout, QWidget, QPushButton

from clicky.design_system import DS


class OutputWidget(QWidget):
    """Frameless floating output panel. Slides open when the AI starts responding."""

    WIDTH = 300
    HEIGHT = 300
    ANIM_DURATION_MS = 280

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("OutputWidget")

        self.setStyleSheet(f"""
            QWidget#OutputWidget {{
                background-color: {DS.Colors.light_bg};
                border-radius: 8px;
                border: 1px solid {DS.Colors.light_border};
            }}
        """)

        self._text_edit = QPlainTextEdit(self)
        self._text_edit.setReadOnly(True)
        self._text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._text_edit.setFont(QFont("Segoe UI", 10))
        self._text_edit.setStyleSheet(
            f"background: transparent; color: {DS.Colors.light_text}; border: none; padding: 8px;"
        )

        self._progress_bar = QProgressBar(self)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("Step %v of %m")
        self._progress_bar.setFixedHeight(16)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {DS.Colors.light_surface};
                border: none;
                border-radius: 4px;
                margin: 0px 8px 6px 8px;
                color: {DS.Colors.light_text_secondary};
                text-align: center;
                font-size: 11px;
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background-color: {DS.Colors.accent_blue};
                border-radius: 4px;
            }}
        """)
        self._progress_bar.hide()

        self._close_btn = QPushButton("×", self)
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {DS.Colors.light_text_secondary};
                border: none;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {DS.Colors.light_text};
            }}
        """)
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.clicked.connect(self.clear_and_hide)
        self._close_btn.move(self.WIDTH - 28, 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._text_edit)
        layout.addWidget(self._progress_bar)

        self._geom_anim = QPropertyAnimation(self, b"geometry")
        self._geom_anim.setDuration(self.ANIM_DURATION_MS)
        self._geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._geom_anim.finished.connect(self._update_height)

        self._thinking = False
        self._thinking_dots = 1
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(500)
        self._thinking_timer.timeout.connect(self._tick_thinking)

        self._fade_out_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_out_anim.setDuration(320)
        self._fade_out_anim.setStartValue(1.0)
        self._fade_out_anim.setEndValue(0.0)
        self._fade_out_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade_out_anim.finished.connect(self._on_fade_finished)

        # Drag state
        self._drag_offset: QPoint | None = None

    # ------------------------------------------------------------------
    # Drag to move
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Progress bar
    # ------------------------------------------------------------------

    def set_progress(self, current: int, total: int) -> None:
        """Show step progress. Hides bar for single-step responses."""
        if total >= 1:
            self._progress_bar.setRange(0, max(1, total))
            self._progress_bar.setValue(current)
            self._progress_bar.show()
        else:
            self._progress_bar.hide()
        self._update_height()

    def _update_height(self) -> None:
        if self._geom_anim.state() == QPropertyAnimation.State.Running:
            return
        doc_height = int(self._text_edit.document().size().height())
        padding = 16
        prog_h = self._progress_bar.height() + 6 if self._progress_bar.isVisible() else 0
        new_h = max(100, min(300, doc_height + padding + prog_h))
        if new_h != self.height():
            self.setFixedHeight(new_h)

    # ------------------------------------------------------------------
    # Animation + content
    # ------------------------------------------------------------------

    def show_animated(self, anchor_x: int, anchor_y: int) -> None:
        """Animate the widget growing from (anchor_x, anchor_y) down-right."""
        self._text_edit.clear()
        self._progress_bar.hide()
        
        target_w = self.WIDTH
        target_h = 100
        
        from PySide6.QtWidgets import QApplication
        screen = QApplication.screenAt(QPoint(anchor_x, anchor_y))
        if screen is None:
            screen = QApplication.primaryScreen()
        geo = screen.geometry()
        
        if anchor_x + target_w > geo.right():
            anchor_x = geo.right() - target_w
        if anchor_y + 300 > geo.bottom():
            anchor_y = geo.bottom() - 300
            
        anchor_x = max(geo.left(), anchor_x)
        anchor_y = max(geo.top(), anchor_y)

        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._geom_anim.stop()
        self.setGeometry(QRect(anchor_x, anchor_y, 1, 1))
        self.show()
        self._geom_anim.setStartValue(QRect(anchor_x, anchor_y, 1, 1))
        self._geom_anim.setEndValue(QRect(anchor_x, anchor_y, target_w, target_h))
        self._geom_anim.start()

    def append_delta(self, text: str) -> None:
        """Append a streaming chunk and scroll to bottom."""
        was_thinking = self._thinking
        self.stop_thinking()
        if was_thinking:
            self._text_edit.clear()
        self._text_edit.insertPlainText(text)
        sb = self._text_edit.verticalScrollBar()
        sb.setValue(sb.maximum())
        self._update_height()

    def set_text(self, text: str) -> None:
        """Replace the full text content and scroll to bottom."""
        self._text_edit.setPlainText(text)
        sb = self._text_edit.verticalScrollBar()
        sb.setValue(sb.maximum())
        self._update_height()

    def _show_direct(self, anchor_x: int, anchor_y: int) -> None:
        """Show at full size immediately — no grow animation, used for thinking state."""
        self._text_edit.clear()
        self._progress_bar.hide()

        target_w = self.WIDTH
        target_h = 100

        from PySide6.QtWidgets import QApplication
        screen = QApplication.screenAt(QPoint(anchor_x, anchor_y))
        if screen is None:
            screen = QApplication.primaryScreen()
        geo = screen.geometry()
        if anchor_x + target_w > geo.right():
            anchor_x = geo.right() - target_w
        if anchor_y + target_h > geo.bottom():
            anchor_y = geo.bottom() - target_h
        anchor_x = max(geo.left(), anchor_x)
        anchor_y = max(geo.top(), anchor_y)

        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._geom_anim.stop()
        self.setGeometry(QRect(anchor_x, anchor_y, target_w, target_h))
        self.show()

    def show_thinking(self, anchor_x: int, anchor_y: int) -> None:
        """Show the output box with animated thinking dots during PROCESSING."""
        if not self.isVisible():
            self._show_direct(anchor_x, anchor_y)
        self._thinking = True
        self._thinking_dots = 1
        self._text_edit.setPlainText("Thinking.")
        self._thinking_timer.start()

    def stop_thinking(self) -> None:
        """Stop thinking animation. Caller is responsible for clearing text if needed."""
        if not self._thinking:
            return
        self._thinking = False
        self._thinking_timer.stop()

    def _tick_thinking(self) -> None:
        self._thinking_dots = (self._thinking_dots % 3) + 1
        self._text_edit.setPlainText("Thinking" + "." * self._thinking_dots)

    def clear_and_hide(self) -> None:
        """Instantly clear text and hide — used when a new response is incoming."""
        self._thinking_timer.stop()
        self._thinking = False
        self._fade_out_anim.stop()
        self._text_edit.clear()
        self._progress_bar.hide()
        self.setWindowOpacity(1.0)
        self.hide()

    def fade_and_hide(self) -> None:
        """Fade out then hide — used for auto-dismiss and shake-dismiss."""
        if not self.isVisible():
            return
        self._fade_out_anim.stop()
        self.setWindowOpacity(1.0)
        self._fade_out_anim.start()

    def _on_fade_finished(self) -> None:
        self.hide()
        self.setWindowOpacity(1.0)
        self._text_edit.clear()
        self._progress_bar.hide()
