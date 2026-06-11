"""Map POINT tag coordinates from screenshot image space to real screen pixels."""

from __future__ import annotations

from clicky.point_parser import PointTag
from clicky.screen_capture import ScreenshotImage
from clicky.uia_snap import snap_to_element


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

    # Clamp to image bounds before inverting the scale transform.
    clamped_x = max(0, min(tag.x, shot.image_width_px - 1))
    clamped_y = max(0, min(tag.y, shot.image_height_px - 1))

    real_x = shot.monitor_left + int(clamped_x / shot.scale_x)
    real_y = shot.monitor_top + int(clamped_y / shot.scale_y)
    return snap_to_element(real_x, real_y)
