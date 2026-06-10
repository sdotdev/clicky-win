"""Parse an LLM response containing [POINT:...] tags into discrete steps."""
from __future__ import annotations

import re
from dataclasses import dataclass

from clicky.point_parser import PointTag

# Matches a [POINT:...] tag anywhere in the text (not anchored to end-of-line).
_STEP_RE = re.compile(
    r"\[POINT:(?:none|(\d+)\s*,\s*(\d+)(?::([^\]:\s][^\]:]*?))?(?::screen(\d+))?)\]"
)


@dataclass(frozen=True)
class Step:
    text: str
    point: PointTag | None  # None = display text only, no fly-to


def parse_steps(response: str) -> list[Step]:
    """Split a response into (text, optional point) steps.

    Each [POINT:...] tag ends a step. Text after the last tag (if any)
    becomes a final no-point step. If no tags are found, returns a single
    step with the full response and no point.
    """
    steps: list[Step] = []
    pos = 0
    for m in _STEP_RE.finditer(response):
        text = response[pos : m.start()].strip()
        pos = m.end()
        if m.group(1) is None:
            point = None
        else:
            point = PointTag(
                x=int(m.group(1)),
                y=int(m.group(2)),
                label=m.group(3) or "",
                screen=int(m.group(4)) if m.group(4) else None,
            )
        if text:
            steps.append(Step(text=text, point=point))

    trailing = response[pos:].strip()
    if trailing:
        steps.append(Step(text=trailing, point=None))

    return steps if steps else [Step(text=response.strip(), point=None)]
