"""Handler for the /tasks command."""
from __future__ import annotations
from clicky.commands.router import CommandContext
from clicky import tasks_store



def handle_tasks(args: str, ctx: CommandContext) -> None:
    args = args.strip()
    if ctx.tasks_window is None:
        return

    if not args:
        ctx.tasks_window.toggle_visible()
        return

    parts = args.split(None, 1)
    sub = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if sub == "add" and rest:
        tasks_store.add_task(rest)
        ctx.tasks_window._refresh()
        if not ctx.tasks_window.isVisible():
            ctx.tasks_window.show_top_left()
    elif sub in ("done", "check") and rest:
        try:
            n = int(rest) - 1
            tasks = tasks_store.tasks_for_date()
            if 0 <= n < len(tasks):
                tasks_store.toggle_task(tasks[n].id)
                ctx.tasks_window._refresh()
        except ValueError:
            pass
