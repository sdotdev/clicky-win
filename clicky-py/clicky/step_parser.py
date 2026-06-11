"""Parse an LLM response containing [POINT:...] or [REGION:...] tags into discrete steps."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from clicky.point_parser import PointTag


@dataclass(frozen=True)
class RegionTag:
    x1: int
    y1: int
    x2: int
    y2: int
    label: str = ""


@dataclass(frozen=True)
class AddTaskTag:
    date: str
    text: str


@dataclass(frozen=True)
class ArrowTag:
    x1: int
    y1: int
    x2: int
    y2: int
    label: str = ""
    screen: int | None = None


@dataclass(frozen=True)
class Step:
    text: str
    point: PointTag | None = None   # fly companion to this point
    region: RegionTag | None = None  # dim screen, highlight this rectangle
    arrow: ArrowTag | None = None   # draw animated arrow from p1 to p2
    add_task: AddTaskTag | None = None
    refresh: bool = False


# Combined regex matching either a POINT or REGION step tag.
_ANY_TAG_RE = re.compile(
    r"\[POINT:(?:none"
    r"|(?P<px>\d+)\s*,\s*(?P<py>\d+)"
    r"(?::(?P<plabel>[^\]:\s][^\]:]*?))?(?::screen(?P<pscreen>\d+))?)\]"
    r"|"
    r"\[REGION:(?P<rx1>\d+)\s*,\s*(?P<ry1>\d+)\s*:\s*"
    r"(?P<rx2>\d+)\s*,\s*(?P<ry2>\d+)(?::(?P<rlabel>[^\]]*))?\]"
    r"|"
    r"\[ARROW:(?P<ax1>\d+)\s*,\s*(?P<ay1>\d+)\s*:\s*"
    r"(?P<ax2>\d+)\s*,\s*(?P<ay2>\d+)(?::(?P<alabel>[^\]:]*))?"
    r"(?::screen(?P<ascreen>\d+))?\]"
    r"|"
    r"\[ADD_TASK:(?P<tdate>\d{4}-\d{2}-\d{2}):(?P<ttext>[^\]]+)\]"
    r"|"
    r"\[(?P<refresh>REFRESH)\]"
)


def parse_steps(response: str) -> list[Step]:
    """Split a response into (text, optional point/region) steps.

    Each [POINT:...] or [REGION:...] tag ends a step. Text after the last tag
    becomes a no-action final step. Returns a single step with full text if no
    tags found.
    """
    steps: list[Step] = []
    pos = 0
    for m in _ANY_TAG_RE.finditer(response):
        text = response[pos : m.start()].strip()
        pos = m.end()

        if m.group("rx1") is not None:
            region = RegionTag(
                x1=int(m.group("rx1")),
                y1=int(m.group("ry1")),
                x2=int(m.group("rx2")),
                y2=int(m.group("ry2")),
                label=m.group("rlabel") or "",
            )
            if text:
                steps.append(Step(text=text, region=region))
        elif m.group("ax1") is not None:
            arrow = ArrowTag(
                x1=int(m.group("ax1")),
                y1=int(m.group("ay1")),
                x2=int(m.group("ax2")),
                y2=int(m.group("ay2")),
                label=m.group("alabel") or "",
                screen=int(m.group("ascreen")) if m.group("ascreen") else None,
            )
            steps.append(Step(text=text, arrow=arrow))
        elif m.group("px") is not None:
            point = PointTag(
                x=int(m.group("px")),
                y=int(m.group("py")),
                label=m.group("plabel") or "",
                screen=int(m.group("pscreen")) if m.group("pscreen") else None,
            )
            if text:
                steps.append(Step(text=text, point=point))
        elif m.group("tdate") is not None:
            task_tag = AddTaskTag(date=m.group("tdate"), text=m.group("ttext"))
            if text:
                steps.append(Step(text=text, add_task=task_tag))
            else:
                steps.append(Step(text="", add_task=task_tag))
        elif m.group("refresh") is not None:
            if text:
                steps.append(Step(text=text, refresh=True))
            else:
                steps.append(Step(text="", refresh=True))
        else:
            # [POINT:none] — display text only, no action
            if text:
                steps.append(Step(text=text))

    trailing = response[pos:].strip()
    if trailing:
        steps.append(Step(text=trailing))

    return steps if steps else [Step(text=response.strip())]
