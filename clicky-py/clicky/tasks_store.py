"""Persistent task storage — JSON file in user data directory."""
from __future__ import annotations
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from platformdirs import user_data_dir

APP_NAME = "ClickyWin"

@dataclass
class Task:
    id: str
    text: str
    done: bool
    date: str        # ISO "YYYY-MM-DD"
    created_at: str  # ISO datetime string

    @staticmethod
    def new(text: str, for_date: str | None = None) -> "Task":
        return Task(
            id=uuid.uuid4().hex,
            text=text,
            done=False,
            date=for_date or date.today().isoformat(),
            created_at=datetime.now().isoformat(),
        )

def _store_path() -> Path:
    p = Path(user_data_dir(APP_NAME, appauthor=False)) / "tasks.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def load() -> dict[str, list[Task]]:
    """Load all tasks keyed by ISO date string."""
    p = _store_path()
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return {
            date_key: [Task(**t) for t in tasks]
            for date_key, tasks in raw.items()
        }
    except Exception:
        return {}

def save(data: dict[str, list[Task]]) -> None:
    """Atomic save via temp file."""
    p = _store_path()
    tmp = p.with_suffix(".tmp")
    serialized = {k: [asdict(t) for t in v] for k, v in data.items()}
    tmp.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    tmp.replace(p)

def tasks_for_date(for_date: str | None = None) -> list[Task]:
    d = for_date or date.today().isoformat()
    return load().get(d, [])

def add_task(text: str, for_date: str | None = None) -> Task:
    data = load()
    task = Task.new(text, for_date)
    data.setdefault(task.date, []).append(task)
    save(data)
    return task

def toggle_task(task_id: str) -> bool:
    """Toggle done state. Returns new done state, or False if not found."""
    data = load()
    for tasks in data.values():
        for t in tasks:
            if t.id == task_id:
                t.done = not t.done
                save(data)
                return t.done
    return False

def delete_task(task_id: str) -> None:
    data = load()
    for date_key in list(data.keys()):
        data[date_key] = [t for t in data[date_key] if t.id != task_id]
        if not data[date_key]:
            del data[date_key]
    save(data)
