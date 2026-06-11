"""Slash-command handlers for the viral effect overlays.

``/power``     — toggle Power Mode (particle cursor + combo meter).
``/celebrate`` — fire a fireworks + confetti burst.
``/scan``      — run the Neon Scan HUD (AI vision, or demo mode).
``/focus``     — toggle Focus Spotlight (dims everything except active window).
``/heatmap``   — toggle Live Click Heatmap overlay.
``/clipboard`` — show Clipboard Ring HUD.

These read widgets/config off the :class:`CommandContext`, which app.py
populates. Real-mode scanning is async; demo mode is instant and offline.
"""

from __future__ import annotations

import asyncio
import base64
import logging

from clicky.commands.router import CommandContext
from clicky.effects.scan_layout import demo_boxes, parse_scan_boxes

logger = logging.getLogger(__name__)


def handle_power(args: str, ctx: CommandContext) -> None:
    widget = getattr(ctx, "power_mode", None)
    if widget is None:
        return
    arg = args.strip().lower()
    if arg in ("on", "start", "enable"):
        widget.set_enabled(True)
    elif arg in ("off", "stop", "disable"):
        widget.set_enabled(False)
    else:
        widget.toggle()


def handle_celebrate(args: str, ctx: CommandContext) -> None:
    widget = getattr(ctx, "celebration", None)
    if widget is None:
        return
    intensity = 1.0
    arg = args.strip().lower()
    if arg in ("big", "max", "huge"):
        intensity = 1.8
    elif arg in ("small", "mini"):
        intensity = 0.5
    widget.celebrate(intensity=intensity)


def handle_scan(args: str, ctx: CommandContext) -> None:
    widget = getattr(ctx, "neon_scan", None)
    if widget is None:
        return

    arg = args.strip().lower()
    cfg = getattr(ctx, "config", None)
    demo = getattr(cfg, "neon_scan_demo", True) if cfg is not None else True
    if arg == "demo":
        demo = True
    elif arg in ("live", "real", "ai"):
        demo = False

    if demo:
        _start_demo(widget)
        return

    mgr = ctx.companion_manager
    companion = getattr(ctx, "companion", None)
    if mgr is None:
        logger.info("Neon Scan: no AI manager, falling back to demo")
        _start_demo(widget)
        return
    asyncio.ensure_future(_run_live_scan(widget, mgr, companion))


def _start_demo(widget) -> None:  # noqa: ANN001
    from PySide6.QtWidgets import QApplication

    geo = QApplication.primaryScreen().virtualGeometry()
    boxes = demo_boxes(geo.width(), geo.height(), count=10)
    # Offset into global screen space (start() converts back to local).
    shifted = [
        type(b)(b.x1 + geo.x(), b.y1 + geo.y(), b.x2 + geo.x(), b.y2 + geo.y(),
                b.label, b.color_index)
        for b in boxes
    ]
    widget.start(shifted, demo=True)


async def _run_live_scan(widget, mgr, companion) -> None:  # noqa: ANN001
    """Capture the screen, ask the vision model for UI boxes, then render."""
    from clicky.prompts import SCAN_SYSTEM_PROMPT

    try:
        if companion is not None:
            companion.hide_for_capture()
        await asyncio.sleep(0.05)
        screenshots = await asyncio.to_thread(mgr._screen_capture_fn)
        if companion is not None:
            companion.restore_after_capture()
    except Exception as exc:  # noqa: BLE001
        logger.error("Neon Scan capture failed: %s", exc)
        _start_demo(widget)
        return

    if not screenshots:
        _start_demo(widget)
        return

    shot = screenshots[0]
    b64 = base64.b64encode(shot.jpeg_bytes).decode()
    messages = [{"role": "user", "content": [
        {"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg", "data": b64}},
        {"type": "text", "text": "Detect the UI elements and output BOX tags."},
    ]}]
    try:
        response = await mgr._llm.send(
            messages, system=SCAN_SYSTEM_PROMPT,
            model=mgr._current_model, max_tokens=1024,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Neon Scan LLM call failed: %s — using demo", exc)
        _start_demo(widget)
        return

    boxes = parse_scan_boxes(
        response,
        image_width=shot.image_width_px,
        image_height=shot.image_height_px,
        screen_width=shot.display_width_px,
        screen_height=shot.display_height_px,
        origin_x=shot.monitor_left,
        origin_y=shot.monitor_top,
    )
    if not boxes:
        logger.info("Neon Scan: model returned no boxes — using demo")
        _start_demo(widget)
        return
    widget.start(boxes, demo=False)


def handle_focus(args: str, ctx: CommandContext) -> None:
    widget = getattr(ctx, "focus_overlay", None)
    if widget is None:
        return
    arg = args.strip().lower()
    if arg in ("on", "start", "enable"):
        widget.set_enabled(True)
    elif arg in ("off", "stop", "disable"):
        widget.set_enabled(False)
    else:
        widget.toggle()


def handle_heatmap(args: str, ctx: CommandContext) -> None:
    widget = getattr(ctx, "heatmap_overlay", None)
    if widget is None:
        return
    arg = args.strip().lower()
    if arg in ("on", "start", "enable"):
        widget.set_enabled(True)
    elif arg in ("off", "stop", "disable"):
        widget.set_enabled(False)
    else:
        widget.toggle()


def handle_clipboard(args: str, ctx: CommandContext) -> None:
    widget = getattr(ctx, "clipboard_ring", None)
    if widget is None:
        return
    widget.show_ring()
