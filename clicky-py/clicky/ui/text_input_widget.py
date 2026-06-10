"""Floating text input widget for keyboard-driven queries."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QWidget

from clicky.design_system import DS


class TextInputWidget(QWidget):
    """Frameless floating text input. Appears near companion on Shift+hotkey."""

    submitted = Signal(str)
    cancelled = Signal()

    WIDTH = 320
    HEIGHT = 36
    ANIM_DURATION_MS = 280

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)

        self._edit = QLineEdit(self)
        self._edit.setPlaceholderText("Type your query…")
        self._edit.setFont(QFont("Segoe UI", 11))
        self._edit.installEventFilter(self)
        self._edit.textChanged.connect(self._on_text_changed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self._edit)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {DS.Colors.surface};
                border: 1px solid {DS.Colors.accent_blue};
                border-radius: 6px;
            }}
            QLineEdit {{
                background: transparent;
                border: none;
                color: {DS.Colors.text_primary};
                padding: 2px 4px;
            }}
        """)

        self._geom_anim = QPropertyAnimation(self, b"geometry")
        self._geom_anim.setDuration(self.ANIM_DURATION_MS)
        self._geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._geom_anim.finished.connect(self._on_anim_finished)
        self._anchor_x = 0
        self._anchor_y = 0

        # Command autocomplete popup
        self._commands: list[str] = []
        self._popup = QListWidget()
        self._popup.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self._popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._popup.setStyleSheet(f"""
            QListWidget {{
                background-color: {DS.Colors.surface};
                border: 1px solid {DS.Colors.accent_blue};
                border-radius: 4px;
                color: {DS.Colors.text_primary};
                font-family: "Segoe UI";
                font-size: 11px;
                padding: 2px;
            }}
            QListWidget::item:selected {{
                background-color: {DS.Colors.accent_blue};
                color: white;
            }}
            QListWidget::item:hover {{
                background-color: {DS.Colors.border};
            }}
        """)
        self._popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._popup.itemClicked.connect(self._on_popup_item_clicked)

    def set_commands(self, names: list[str]) -> None:
        """Provide the list of available slash commands (without the leading slash)."""
        self._commands = names

    def show_near(self, x: int, y: int) -> None:
        """Show the widget near the given screen coordinates (no animation)."""
        self._edit.clear()
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.move(x, y)
        self.show()
        self.activateWindow()
        self._edit.setFocus()

    def show_animated(self, anchor_x: int, anchor_y: int) -> None:
        """Animate the widget growing from (anchor_x, anchor_y) down-right."""
        self._anchor_x = anchor_x
        self._anchor_y = anchor_y
        self._edit.clear()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._geom_anim.stop()
        self.setGeometry(QRect(anchor_x, anchor_y, 1, 1))
        self.show()
        self._geom_anim.setStartValue(QRect(anchor_x, anchor_y, 1, 1))
        self._geom_anim.setEndValue(QRect(anchor_x, anchor_y, self.WIDTH, self.HEIGHT))
        self._geom_anim.start()

    def _on_anim_finished(self) -> None:
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.activateWindow()
        self._edit.setFocus()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._hide_popup()
        super().hideEvent(event)

    # ------------------------------------------------------------------
    # Autocomplete
    # ------------------------------------------------------------------

    def _on_text_changed(self, text: str) -> None:
        stripped = text.lstrip()
        if stripped.startswith("/") and " " not in stripped:
            query = stripped[1:].lower()
            matches = [c for c in self._commands if c.startswith(query)]
            if matches:
                self._show_popup(matches)
            else:
                self._hide_popup()
        else:
            self._hide_popup()

    def _show_popup(self, matches: list[str]) -> None:
        self._popup.clear()
        for name in matches:
            self._popup.addItem(f"/{name}")
        row_h = self._popup.sizeHintForRow(0) if matches else 24
        visible_rows = min(len(matches), 6)
        h = row_h * visible_rows + 8
        self._popup.setFixedSize(QSize(self.WIDTH, h))

        global_pos: QPoint = self.mapToGlobal(QPoint(0, self.HEIGHT))
        self._popup.move(global_pos)
        self._popup.show()

    def _hide_popup(self) -> None:
        self._popup.hide()
        self._popup.clearSelection()

    def _on_popup_item_clicked(self, item: QListWidgetItem) -> None:
        self._edit.setText(item.text())
        self._hide_popup()
        self.activateWindow()
        self._edit.setFocus()

    # ------------------------------------------------------------------
    # Event filter — keyboard nav for popup + submit/cancel
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if obj is self._edit and isinstance(event, QKeyEvent):
            if self._popup.isVisible():
                if event.key() == Qt.Key.Key_Down:
                    cur = self._popup.currentRow()
                    self._popup.setCurrentRow(min(cur + 1, self._popup.count() - 1))
                    return True
                if event.key() == Qt.Key.Key_Up:
                    cur = self._popup.currentRow()
                    self._popup.setCurrentRow(max(cur - 1, 0))
                    return True
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                    item = self._popup.currentItem()
                    if item is not None:
                        self._on_popup_item_clicked(item)
                        return True
                if event.key() == Qt.Key.Key_Escape:
                    self._hide_popup()
                    return True

            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                text = self._edit.text().strip()
                if text:
                    self.submitted.emit(text)
                self.hide()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self._hide_popup()
                self.cancelled.emit()
                self.hide()
                return True
        return super().eventFilter(obj, event)
