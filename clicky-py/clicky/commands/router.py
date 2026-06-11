"""Slash-command router."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CommandContext:
    """Passed to every command handler."""
    tasks_window: Any = None        # TasksWindow | None
    companion_manager: Any = None   # CompanionManager | None
    companion: Any = None           # CompanionWidget | None
    swarm_overlay: Any = None       # SwarmOverlayWidget | None


class CommandRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[str, CommandContext], None]] = {}

    def register(self, name: str, handler: Callable[[str, CommandContext], None]) -> None:
        """Register a command. name should be lowercase without the slash."""
        self._handlers[name.lower().lstrip("/")] = handler

    def command_names(self) -> list[str]:
        """Return sorted list of registered command names (without the leading slash)."""
        return sorted(self._handlers.keys())

    def dispatch(self, text: str, ctx: CommandContext) -> bool:
        """Return True if text was a slash command (handled), False otherwise."""
        text = text.strip()
        if not text.startswith("/"):
            return False
        parts = text[1:].split(None, 1)
        if not parts:
            return False
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        import difflib
        matches = difflib.get_close_matches(cmd, self._handlers.keys(), n=1, cutoff=0.7)
        if not matches:
            return False
            
        handler = self._handlers[matches[0]]
        handler(args, ctx)
        return True
