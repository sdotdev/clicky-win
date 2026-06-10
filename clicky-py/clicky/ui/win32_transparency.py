"""Win32 helper: apply DWM per-pixel alpha transparency to a Qt window."""
from __future__ import annotations

import ctypes
import sys


def apply_win32_transparency(hwnd: int) -> None:
    """Apply WS_EX_LAYERED + DWM frame extension for per-pixel alpha.

    No-op on non-Windows platforms.
    """
    if sys.platform != "win32":
        return

    try:
        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi

        GWL_EXSTYLE = -20  # noqa: N806
        WS_EX_LAYERED = 0x00080000  # noqa: N806

        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)

        # Disable non-client rendering so DWM does not paint a border.
        DWMWA_NCRENDERING_POLICY = 2  # noqa: N806
        policy = ctypes.c_int(1)  # DWMNCRP_DISABLED
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_NCRENDERING_POLICY,
            ctypes.byref(policy), ctypes.sizeof(policy),
        )

        # Extend frame into client area (all sides = -1 for full sheet-of-glass).
        class MARGINS(ctypes.Structure):  # noqa: N801
            _fields_ = [
                ("left", ctypes.c_int), ("right", ctypes.c_int),
                ("top", ctypes.c_int), ("bottom", ctypes.c_int),
            ]

        margins = MARGINS(-1, -1, -1, -1)
        dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))

    except Exception:  # noqa: BLE001
        pass  # Silently ignore on unsupported configurations.
