"""Map POINT tag coordinates from screenshot image space to real screen pixels."""

from __future__ import annotations

from clicky.point_parser import PointTag
from clicky.screen_capture import ScreenshotImage


def map_point_to_screen(
    tag: PointTag,
    screenshots: list[ScreenshotImage],
) -> tuple[int, int] | None:
    """Map POINT tag coordinates to absolute screen pixels.

    Args:
        tag: Parsed POINT tag with x, y in screenshot image space.
        screenshots: Captured screenshots with scale and monitor offset metadata.

    Returns:
        (real_x, real_y) in global screen coordinates, or None if no screenshots.
    """
    if not screenshots:
        return None

    # Select target screenshot (1-indexed screen number)
    if tag.screen is not None and 1 <= tag.screen <= len(screenshots):
        shot = screenshots[tag.screen - 1]
    else:
        shot = screenshots[0]  # cursor's screen (first in list)

    real_x = int(shot.monitor_left / shot.dpi_scale) + int(tag.x / shot.scale / shot.dpi_scale)
    real_y = int(shot.monitor_top  / shot.dpi_scale) + int(tag.y / shot.scale / shot.dpi_scale)
    return (real_x, real_y)
