"""Detection-box sourcing for the Neon Scan HUD overlay.

Two sources feed the same :class:`ScanBox` shape:

* **Demo mode** — :func:`demo_boxes` synthesises a convincing, well-distributed
  set of labelled boxes for a given screen size. No screenshot, no network.
* **Real mode** — :func:`parse_scan_boxes` extracts ``[BOX:x1,y1:x2,y2:label]``
  tags from a vision-model response and maps them into screen pixels.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

_BOX_TAG_RE = re.compile(
    r"\[BOX:\s*(\d+)\s*,\s*(\d+)\s*:\s*(\d+)\s*,\s*(\d+)\s*:([^\]]*)\]"
)

# Plausible UI-element labels for demo mode, in a cyber-HUD register.
_DEMO_LABELS = [
    "nav_bar", "primary_button", "search_field", "menu_item", "toolbar",
    "icon_button", "tab_strip", "panel_header", "list_item", "status_bar",
    "input_field", "dropdown", "avatar", "card", "scrollbar", "tooltip",
    "breadcrumb", "checkbox", "slider", "badge",
]


@dataclass(frozen=True)
class ScanBox:
    """An axis-aligned detection box in screen pixels with a label and colour."""

    x1: int
    y1: int
    x2: int
    y2: int
    label: str
    color_index: int = 0

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def cy(self) -> int:
        return (self.y1 + self.y2) // 2


def demo_boxes(
    width: int,
    height: int,
    *,
    count: int = 9,
    seed: int | None = None,
) -> list[ScanBox]:
    """Generate a tasteful, non-overlapping-ish set of demo detection boxes.

    Boxes are scattered across the screen at element-like sizes and sorted top
    to bottom so they lock on in reading order as the scan line descends.
    """
    rng = random.Random(seed)
    boxes: list[ScanBox] = []
    attempts = 0
    margin_x = int(width * 0.04)
    margin_y = int(height * 0.05)

    def overlaps(a: ScanBox, b: ScanBox) -> bool:
        return not (
            a.x2 < b.x1 - 12 or a.x1 > b.x2 + 12
            or a.y2 < b.y1 - 12 or a.y1 > b.y2 + 12
        )

    labels = _DEMO_LABELS[:]
    rng.shuffle(labels)

    while len(boxes) < count and attempts < count * 40:
        attempts += 1
        bw = rng.randint(int(width * 0.07), int(width * 0.26))
        bh = rng.randint(int(height * 0.045), int(height * 0.16))
        x1 = rng.randint(margin_x, max(margin_x + 1, width - margin_x - bw))
        y1 = rng.randint(margin_y, max(margin_y + 1, height - margin_y - bh))
        candidate = ScanBox(
            x1=x1, y1=y1, x2=x1 + bw, y2=y1 + bh,
            label=labels[len(boxes) % len(labels)],
            color_index=len(boxes),
        )
        if any(overlaps(candidate, b) for b in boxes):
            continue
        boxes.append(candidate)

    boxes.sort(key=lambda b: b.y1)
    # Reassign colour index after sorting so colours cycle in lock-on order.
    return [
        ScanBox(b.x1, b.y1, b.x2, b.y2, b.label, color_index=i)
        for i, b in enumerate(boxes)
    ]


def parse_scan_boxes(
    response: str,
    *,
    image_width: int,
    image_height: int,
    screen_width: int,
    screen_height: int,
    origin_x: int = 0,
    origin_y: int = 0,
) -> list[ScanBox]:
    """Parse ``[BOX:...]`` tags from a model response into screen-space boxes.

    Coordinates in the response are in image space (``image_width`` ×
    ``image_height``); they are rescaled to the real screen and offset by the
    monitor origin. Malformed or zero-area boxes are skipped.
    """
    sx = screen_width / image_width if image_width else 1.0
    sy = screen_height / image_height if image_height else 1.0

    out: list[ScanBox] = []
    for m in _BOX_TAG_RE.finditer(response):
        ix1, iy1, ix2, iy2 = (int(m.group(i)) for i in range(1, 5))
        label = m.group(5).strip() or "element"
        x1, x2 = sorted((ix1, ix2))
        y1, y2 = sorted((iy1, iy2))
        rx1 = origin_x + int(x1 * sx)
        ry1 = origin_y + int(y1 * sy)
        rx2 = origin_x + int(x2 * sx)
        ry2 = origin_y + int(y2 * sy)
        if rx2 - rx1 < 4 or ry2 - ry1 < 4:
            continue
        out.append(ScanBox(rx1, ry1, rx2, ry2, label, color_index=len(out)))

    out.sort(key=lambda b: b.y1)
    return [
        ScanBox(b.x1, b.y1, b.x2, b.y2, b.label, color_index=i)
        for i, b in enumerate(out)
    ]
