"""Tasks panel — floating 300×400 to-do list."""
from __future__ import annotations

import time
from datetime import date, timedelta

from PySide6.QtCore import QEvent, Qt, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from clicky.design_system import DS
from clicky.tasks_store import add_task, delete_task, tasks_for_date, toggle_task


class TasksWindow(QWidget):
    WIDTH = 300
    HEIGHT = 400

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_date: str = date.today().isoformat()
        self._opened_at: float = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._drag_offset: QPoint | None = None

        self.setStyleSheet(
            f"QWidget#tasks_root {{"
            f"  background-color: {DS.Colors.panel_bg};"
            f"  border: 1px solid {DS.Colors.border};"
            f"  border-radius: 8px;"
            f"}}"
        )

        root = QWidget(self)
        root.setObjectName("tasks_root")
        root.setStyleSheet(
            f"background-color: {DS.Colors.panel_bg};"
            f"border: 1px solid {DS.Colors.border};"
            f"border-radius: 8px;"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)
        
        root.installEventFilter(self)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header row
        header = QHBoxLayout()
        btn_style = (
            f"QPushButton {{"
            f"  background: transparent;"
            f"  color: {DS.Colors.text_primary};"
            f"  border: none;"
            f"  font-size: 14px;"
            f"  padding: 2px 6px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {DS.Colors.surface}; border-radius: 4px; }}"
        )
        self._prev_btn = QPushButton("←")
        self._prev_btn.setStyleSheet(btn_style)
        self._prev_btn.setFixedWidth(28)
        self._prev_btn.clicked.connect(self._go_prev_day)

        self._date_label = QLabel()
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._date_label.setStyleSheet(
            f"color: {DS.Colors.text_primary}; font-size: 12px; font-weight: bold;"
        )
        self._date_label.installEventFilter(self)

        self._next_btn = QPushButton("→")
        self._next_btn.setStyleSheet(btn_style)
        self._next_btn.setFixedWidth(28)
        self._next_btn.clicked.connect(self._go_next_day)

        header.addWidget(self._prev_btn)
        header.addWidget(self._date_label, 1)
        header.addWidget(self._next_btn)
        
        close_btn = QPushButton("×")
        close_btn.setStyleSheet(btn_style)
        close_btn.setFixedWidth(28)
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)
        
        layout.addLayout(header)

        # Scroll area for tasks
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: transparent; }}"
            f"QScrollBar:vertical {{ background: {DS.Colors.surface}; width: 6px; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical {{ background: {DS.Colors.border}; border-radius: 3px; }}"
        )

        self._task_container = QWidget()
        self._task_container.setStyleSheet("background: transparent;")
        self._task_layout = QVBoxLayout(self._task_container)
        self._task_layout.setContentsMargins(0, 0, 0, 0)
        self._task_layout.setSpacing(2)
        self._task_layout.addStretch()

        self._scroll.setWidget(self._task_container)
        layout.addWidget(self._scroll, 1)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(4)

        self._new_task_edit = QLineEdit()
        self._new_task_edit.setPlaceholderText("Add a task...")
        self._new_task_edit.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {DS.Colors.surface};"
            f"  color: {DS.Colors.text_primary};"
            f"  border: 1px solid {DS.Colors.border};"
            f"  border-radius: 4px;"
            f"  padding: 4px 6px;"
            f"  font-size: 12px;"
            f"}}"
        )
        self._new_task_edit.returnPressed.connect(self._add_task_from_input)

        add_btn = QPushButton("Add")
        add_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {DS.Colors.accent_blue};"
            f"  color: {DS.Colors.text_white};"
            f"  border: none;"
            f"  border-radius: 4px;"
            f"  padding: 4px 10px;"
            f"  font-size: 12px;"
            f"}}"
            f"QPushButton:hover {{ background-color: #3a8eef; }}"
        )
        add_btn.clicked.connect(self._add_task_from_input)

        footer.addWidget(self._new_task_edit, 1)
        footer.addWidget(add_btn)
        layout.addLayout(footer)

        self._refresh()

    # ------------------------------------------------------------------
    # Drag to move
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = event.globalPosition().toPoint() - self.pos()
        elif event.type() == QEvent.Type.MouseMove:
            if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = None
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _go_prev_day(self) -> None:
        d = date.fromisoformat(self._current_date) - timedelta(days=1)
        self._current_date = d.isoformat()
        self._refresh()

    def _go_next_day(self) -> None:
        d = date.fromisoformat(self._current_date) + timedelta(days=1)
        self._current_date = d.isoformat()
        self._refresh()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        today = date.today().isoformat()
        label = f"Today — {self._current_date}" if self._current_date == today else self._current_date
        self._date_label.setText(label)

        # Clear existing task rows (leave the stretch at end)
        while self._task_layout.count() > 1:
            item = self._task_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tasks = tasks_for_date(self._current_date)
        for task in tasks:
            row = self._make_task_row(task)
            self._task_layout.insertWidget(self._task_layout.count() - 1, row)

    def _make_task_row(self, task) -> QWidget:
        row = QWidget()
        row.setStyleSheet(
            f"QWidget {{ background-color: {DS.Colors.surface}; border-radius: 4px; }}"
        )
        h = QHBoxLayout(row)
        h.setContentsMargins(6, 4, 4, 4)
        h.setSpacing(4)

        cb = QCheckBox()
        cb.setChecked(task.done)

        if task.done:
            cb.setText(f"<s>{task.text}</s>")
            cb.setStyleSheet(
                f"QCheckBox {{ color: {DS.Colors.text_secondary}; font-size: 12px; }}"
                f"QCheckBox::indicator {{ width: 14px; height: 14px; }}"
            )
        else:
            cb.setText(task.text)
            cb.setStyleSheet(
                f"QCheckBox {{ color: {DS.Colors.text_primary}; font-size: 12px; }}"
                f"QCheckBox::indicator {{ width: 14px; height: 14px; }}"
            )

        task_id = task.id

        def on_toggle(_state, tid=task_id):
            toggle_task(tid)
            self._refresh()

        cb.stateChanged.connect(on_toggle)

        del_btn = QPushButton("×")
        del_btn.setFixedSize(18, 18)
        del_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent;"
            f"  color: {DS.Colors.text_secondary};"
            f"  border: none;"
            f"  font-size: 13px;"
            f"  padding: 0;"
            f"}}"
            f"QPushButton:hover {{ color: {DS.Colors.error_red}; }}"
        )

        def on_delete(tid=task_id):
            delete_task(tid)
            self._refresh()

        del_btn.clicked.connect(on_delete)

        h.addWidget(cb, 1)
        h.addWidget(del_btn)
        return row

    # ------------------------------------------------------------------
    # Footer actions
    # ------------------------------------------------------------------

    def _add_task_from_input(self) -> None:
        text = self._new_task_edit.text().strip()
        if not text:
            return
        add_task(text, self._current_date)
        self._new_task_edit.clear()
        self._refresh()

    # ------------------------------------------------------------------
    # Visibility helpers
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()

    def show_top_left(self) -> None:
        self._opened_at = time.monotonic()
        screen = QApplication.primaryScreen()
        geo = screen.geometry()
        self.move(geo.x() + 16, geo.y() + 16)
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle_visible(self) -> None:
        if self.isVisible():
            if time.monotonic() - self._opened_at < 1.5:
                return  # grace period — ignore spurious close within 1.5s of opening
            self.hide()
        else:
            self.show_top_left()

    # ------------------------------------------------------------------
    # Context for LLM
    # ------------------------------------------------------------------

    def get_tasks_context(self) -> str:
        tasks = tasks_for_date()
        if not tasks:
            return "The user has no tasks for today."
        lines = ["User's tasks for today:"]
        for i, t in enumerate(tasks, 1):
            status = "✓" if t.done else "○"
            lines.append(f"  {i}. [{status}] {t.text}")
        return "\n".join(lines)
