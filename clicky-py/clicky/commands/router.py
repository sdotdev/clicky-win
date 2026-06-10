"""Slash-command router."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CommandContext:
    """Passed to every command handler."""
    tasks_window: Any = None   # TasksWindow | None
    companion_manager: Any = None  # CompanionManager | None


class CommandRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[str, CommandContext], None]] = {}

    def register(self, name: str, handler: Callable[[str, CommandContext], None]) -> None:
        """Register a command. name should be lowercase without the slash."""
        self._handlers[name.lower().lstrip("/")] = handler

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
        handler = self._handlers.get(cmd)
        if handler is None:
            return False
        handler(args, ctx)
        return True
