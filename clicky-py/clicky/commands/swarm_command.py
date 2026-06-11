"""Handler for the /swarm command — visual orbit by default; real actions for folder-sort in Explorer."""
from __future__ import annotations

import asyncio
import base64
import ctypes
import logging
import re
from dataclasses import dataclass
from typing import Any

from clicky.commands.router import CommandContext

logger = logging.getLogger(__name__)

_SWARM_TAG_RE = re.compile(r'\[SWARM:(\d+),(\d+):([^\]:]*):([^\]]*)\]')

_SORT_WORDS = {"sort", "organise", "organize", "clean", "arrange", "group", "tidy"}
_EXPLORER_TITLES = {"file explorer", "explorer", "this pc", "downloads", "documents", "desktop"}


@dataclass
class SwarmAction:
    x: int
    y: int
    cmd: str    # PowerShell command — empty = visual-only
    label: str


def parse_swarm_actions(text: str) -> list[SwarmAction]:
    actions = []
    for m in _SWARM_TAG_RE.finditer(text):
        actions.append(SwarmAction(
            x=int(m.group(1)),
            y=int(m.group(2)),
            cmd=m.group(3).strip(),
            label=m.group(4).strip(),
        ))
    return actions


def _is_folder_sort(task: str, window_title: str) -> bool:
    """True only when task is explicitly about sorting/organising AND File Explorer is active."""
    task_low = task.lower()
    title_low = window_title.lower()
    has_sort = any(w in task_low for w in _SORT_WORDS)
    has_explorer = any(w in title_low for w in _EXPLORER_TITLES)
    return has_sort and has_explorer


def _get_foreground_window_center() -> tuple[int, int] | None:
    """Return screen-space centre of the foreground window, or None on failure."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        rect = ctypes.wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        return cx, cy
    except Exception:  # noqa: BLE001
        return None


async def _run_swarm(
    task: str,
    manager: Any,
    companion: Any,
    swarm_overlay: Any,
) -> None:
    from clicky.active_window import get_foreground_window_title
    from PySide6.QtCore import QPointF

    window_title = get_foreground_window_title()

    if _is_folder_sort(task, window_title):
        await _run_folder_sort(task, manager, companion, swarm_overlay, window_title)
    else:
        # Pure visual orbit — no LLM, no screenshot, no network
        swarm_overlay.pending_anchor = None
        swarm_overlay.set_pending_actions([])
        companion.trigger_bounce()


async def _run_folder_sort(
    task: str,
    manager: Any,
    companion: Any,
    swarm_overlay: Any,
    window_title: str,
) -> None:
    from clicky.prompts import SWARM_SYSTEM_PROMPT
    from PySide6.QtCore import QPointF

    companion.hide_for_capture()
    await asyncio.sleep(0.05)
    screenshots = await asyncio.to_thread(manager._screen_capture_fn)
    companion.restore_after_capture()

    actions: list[SwarmAction] = []
    primary_shot = screenshots[0] if screenshots else None

    if screenshots:
        image_blocks: list[dict] = []
        for s in screenshots:
            b64 = base64.b64encode(s.jpeg_bytes).decode()
            image_blocks += [
                {"type": "text", "text": s.label},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
            ]
        messages = [{"role": "user", "content": image_blocks + [
            {"type": "text", "text": f"Task: {task}\nActive window: {window_title}"},
        ]}]
        try:
            response = await manager._llm.send(
                messages,
                system=SWARM_SYSTEM_PROMPT,
                model=manager._current_model,
                max_tokens=512,
            )
            actions = parse_swarm_actions(response)
        except Exception as exc:  # noqa: BLE001
            logger.error("swarm LLM call failed: %s", exc)

    if primary_shot:
        swarm_overlay.set_screen_info(
            scale_x=primary_shot.scale_x,
            scale_y=primary_shot.scale_y,
            monitor_left=primary_shot.monitor_left,
            monitor_top=primary_shot.monitor_top,
        )

    # Set anchor to foreground window centre so agents orbit around the explorer window
    win_center = _get_foreground_window_center()
    if win_center:
        swarm_overlay.pending_anchor = QPointF(win_center[0], win_center[1])
    else:
        swarm_overlay.pending_anchor = None

    swarm_overlay.set_pending_actions(actions)
    companion.trigger_bounce()


def handle_swarm(args: str, ctx: CommandContext) -> None:
    task = args.strip() or "visual"
    mgr = ctx.companion_manager
    if mgr is None:
        return
    companion = getattr(ctx, "companion", None)
    swarm_overlay = getattr(ctx, "swarm_overlay", None)
    if companion is None or swarm_overlay is None:
        return
    asyncio.ensure_future(_run_swarm(task, mgr, companion, swarm_overlay))
