"""Hotkey monitors — re-exports from hotkey_ptt and hotkey_global.

Import from this module for backwards compatibility, or import directly
from the submodules:
    clicky.hotkey_ptt   — HotkeyMonitor (push-to-talk state machine)
    clicky.hotkey_global — GlobalShortcutMonitor (fixed Ctrl+Shift combos)
"""

from clicky.hotkey_global import GlobalShortcutMonitor
from clicky.hotkey_ptt import HotkeyMonitor

__all__ = ["HotkeyMonitor", "GlobalShortcutMonitor"]
