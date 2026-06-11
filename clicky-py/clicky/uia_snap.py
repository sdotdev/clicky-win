"""UI Automation element snapping.

After the model predicts a screen coordinate, query Windows UI Automation for
an interactive element at or near that point and snap to its center. Falls back
to the original coordinate if UIA is unavailable or times out.
"""

from __future__ import annotations

import concurrent.futures
import logging
import sys

logger = logging.getLogger(__name__)

_UIA_TIMEOUT_S = 0.15
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia")

# UIA control pattern IDs for interactive elements.
_ACTIONABLE_PATTERNS = (
    10000,  # UIA_InvokePatternId
    10015,  # UIA_TogglePatternId
    10010,  # UIA_SelectionItemPatternId
    10018,  # UIA_ValuePatternId
    10019,  # UIA_ScrollItemPatternId
)


def _rect_center(rect) -> tuple[int, int]:
    return (
        (rect.left + rect.right) // 2,
        (rect.top + rect.bottom) // 2,
    )


def _is_actionable(element) -> bool:
    for pattern_id in _ACTIONABLE_PATTERNS:
        try:
            result = element.GetCurrentPattern(pattern_id)
            if result:
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def _snap_sync(x: int, y: int) -> tuple[int, int]:
    """Blocking UIA lookup — run inside the thread pool."""
    try:
        import comtypes.client  # type: ignore[import]
        import comtypes.gen.UIAutomationClient as uiac  # type: ignore[import]
    except ImportError:
        return (x, y)

    try:
        uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=uiac.IUIAutomation,
        )

        import comtypes  # noqa: PLC0415
        pt = comtypes.gen.UIAutomationClient.tagPOINT()
        pt.x = x
        pt.y = y
        element = uia.ElementFromPoint(pt)
        if element is None:
            return (x, y)

        if _is_actionable(element):
            rect = element.CurrentBoundingRectangle
            cx, cy = _rect_center(rect)
            logger.debug("UIA snap: (%d,%d) → (%d,%d)", x, y, cx, cy)
            return (cx, cy)

        # Try parent in case we landed on a child label inside a button.
        try:
            parent = element.GetCurrentParent()
            if parent is not None and _is_actionable(parent):
                rect = parent.CurrentBoundingRectangle
                cx, cy = _rect_center(rect)
                logger.debug("UIA snap (parent): (%d,%d) → (%d,%d)", x, y, cx, cy)
                return (cx, cy)
        except Exception:  # noqa: BLE001
            pass

    except Exception as exc:  # noqa: BLE001
        logger.debug("UIA snap error: %s", exc)

    return (x, y)


def snap_to_element(x: int, y: int) -> tuple[int, int]:
    """Return the center of the nearest interactive UIA element, or (x, y) on failure.

    Runs in a thread pool with a hard timeout so it never blocks the UI loop.
    Only available on Windows; returns (x, y) unchanged on other platforms.
    """
    if sys.platform != "win32":
        return (x, y)
    try:
        future = _executor.submit(_snap_sync, x, y)
        return future.result(timeout=_UIA_TIMEOUT_S)
    except concurrent.futures.TimeoutError:
        logger.debug("UIA snap timed out for (%d,%d)", x, y)
        return (x, y)
    except Exception as exc:  # noqa: BLE001
        logger.debug("UIA snap exception: %s", exc)
        return (x, y)
