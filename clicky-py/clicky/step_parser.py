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
class Step:
    text: str
    point: PointTag | None = None   # fly companion to this point
    region: RegionTag | None = None  # dim screen, highlight this rectangle


# Combined regex matching either a POINT or REGION step tag.
_ANY_TAG_RE = re.compile(
    r"\[POINT:(?:none"
    r"|(?P<px>\d+)\s*,\s*(?P<py>\d+)"
    r"(?::(?P<plabel>[^\]:\s][^\]:]*?))?(?::screen(?P<pscreen>\d+))?)\]"
    r"|"
    r"\[REGION:(?P<rx1>\d+)\s*,\s*(?P<ry1>\d+)\s*:\s*"
    r"(?P<rx2>\d+)\s*,\s*(?P<ry2>\d+)(?::(?P<rlabel>[^\]]*))?\]"
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
        elif m.group("px") is not None:
            point = PointTag(
                x=int(m.group("px")),
                y=int(m.group("py")),
                label=m.group("plabel") or "",
                screen=int(m.group("pscreen")) if m.group("pscreen") else None,
            )
            if text:
                steps.append(Step(text=text, point=point))
        else:
            # [POINT:none] — display text only, no action
            if text:
                steps.append(Step(text=text))

    trailing = response[pos:].strip()
    if trailing:
        steps.append(Step(text=trailing))

    return steps if steps else [Step(text=response.strip())]
