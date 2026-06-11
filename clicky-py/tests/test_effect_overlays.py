"""Smoke tests for the practical-visual overlay widgets.

These exercise the non-painting logic: enable/disable state machines,
clipboard history dedupe, ring rotation, and heatmap click pruning.
Runs offscreen so no display is required.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def test_focus_overlay_toggle(app):
    from clicky.ui.focus_overlay_widget import FocusOverlayWidget

    w = FocusOverlayWidget()
    assert w.toggle() is True
    assert w.toggle() is False


def test_focus_overlay_lerps_toward_target(app):
    from PySide6.QtCore import QRectF

    from clicky.ui.focus_overlay_widget import FocusOverlayWidget

    w = FocusOverlayWidget()
    w._enabled = True
    w._spotlight_rect = QRectF(0, 0, 100, 100)
    w._target_rect = QRectF(200, 200, 400, 300)
    w._tick()
    assert 0 < w._spotlight_rect.x() < 200
    assert 100 < w._spotlight_rect.width() < 400


def test_heatmap_toggle_and_prune(app):
    from clicky.ui.heatmap_overlay_widget import HeatmapOverlayWidget

    w = HeatmapOverlayWidget()
    assert w.toggle() is True
    now = time.monotonic()
    w._clicks.append((10.0, 10.0, now))          # fresh — kept
    w._clicks.append((20.0, 20.0, now - 60.0))   # stale — pruned
    w._tick()
    assert len(w._clicks) == 1
    assert w.toggle() is False


def test_clipboard_ring_dedupes_consecutive(app):
    from clicky.ui.clipboard_ring_widget import ClipboardRingWidget

    w = ClipboardRingWidget()
    w._items = []
    clipboard = QApplication.clipboard()
    clipboard.setText("alpha")
    w._on_clipboard_changed()
    w._on_clipboard_changed()  # same text — must not duplicate
    assert w._items == ["alpha"]


def test_clipboard_ring_rotation_wraps(app):
    from clicky.ui.clipboard_ring_widget import ClipboardRingWidget

    w = ClipboardRingWidget()
    w._items = ["a", "b", "c"]
    w._selected = 0
    w._rotate(1)
    assert w._selected == 2  # rotating forward moves selection backward mod n
    w._rotate(-1)
    assert w._selected == 0


def test_clipboard_ring_caps_history(app):
    from clicky.ui import clipboard_ring_widget as mod

    w = mod.ClipboardRingWidget()
    w._items = []
    clipboard = QApplication.clipboard()
    for i in range(mod._MAX_ITEMS + 5):
        clipboard.setText(f"item-{i}")
        w._on_clipboard_changed()
    assert len(w._items) == mod._MAX_ITEMS
    assert w._items[0] == f"item-{mod._MAX_ITEMS + 4}"  # newest first
