from __future__ import annotations

import io
from dataclasses import dataclass

import mss
from PIL import Image
from pynput.mouse import Controller as MouseController

_JPEG_QUALITY = 80

# Supported resolutions that match Computer Use model training data.
# The closest aspect-ratio match is chosen for each captured monitor.
_SUPPORTED_RESOLUTIONS: list[tuple[int, int]] = [
    (1366, 768),   # 16:9
    (1280, 720),   # 16:9
    (1280, 800),   # 16:10
    (1024, 768),   # 4:3
]


def _choose_target_resolution(width: int, height: int) -> tuple[int, int]:
    """Return the supported resolution whose aspect ratio is closest to width/height."""
    aspect = width / height
    return min(_SUPPORTED_RESOLUTIONS, key=lambda r: abs(r[0] / r[1] - aspect))


@dataclass
class ScreenshotImage:
    """A single captured monitor encoded as JPEG."""

    jpeg_bytes: bytes
    label: str
    is_cursor_screen: bool
    display_width_px: int
    display_height_px: int
    image_width_px: int
    image_height_px: int
    scale_x: float         # horizontal downscale ratio (image_w / display_w)
    scale_y: float         # vertical downscale ratio (image_h / display_h)
    monitor_left: int      # global X origin of this monitor
    monitor_top: int       # global Y origin of this monitor
    dpi_scale: float = 1.0  # device pixel ratio from Qt (1.5 on 150%-scaled monitor)


def compose_screen_label(
    screen_index: int, total_screens: int, is_cursor_screen: bool
) -> str:
    """Return a human-readable label for a captured screen.

    When there is only one screen the label is simplified. When multiple
    screens are present, each label includes a 1-based position and whether
    the cursor is currently on that screen.
    """
    if total_screens == 1:
        return "user's screen (cursor is here)"

    position = screen_index + 1
    if is_cursor_screen:
        return f"screen {position} of {total_screens} \u2014 cursor is on this screen (primary focus)"
    return f"screen {position} of {total_screens} \u2014 secondary screen"


def _cursor_in_monitor(cx: int, cy: int, monitor: dict) -> bool:
    """Return True if cursor (cx, cy) is inside *monitor* bounds."""
    return (
        monitor["left"] <= cx < monitor["left"] + monitor["width"]
        and monitor["top"] <= cy < monitor["top"] + monitor["height"]
    )


def capture_all(qt_screens: list | None = None) -> list[ScreenshotImage]:
    """Capture every monitor, returning the cursor screen first.

    Each capture is downscaled so the long edge is at most 1280 px and
    encoded as JPEG quality 80.
    """
    cx, cy = MouseController().position

    with mss.mss() as sct:
        # monitors[0] is the virtual-screen aggregate; skip it.
        physical_monitors = sct.monitors[1:]

        # Tag each monitor with its original index and whether the cursor is on it.
        tagged: list[tuple[int, dict, bool]] = []
        for idx, mon in enumerate(physical_monitors):
            tagged.append((idx, mon, _cursor_in_monitor(cx, cy, mon)))

        # Sort: cursor screen first, then preserve original order.
        tagged.sort(key=lambda t: (not t[2], t[0]))

        results: list[ScreenshotImage] = []
        total = len(tagged)

        for screen_index, (_, mon, is_cursor) in enumerate(tagged):
            # Determine DPI scale by matching monitor center to a Qt screen.
            dpi_scale = 1.0
            if qt_screens:
                center_x = mon["left"] + mon["width"] // 2
                center_y = mon["top"] + mon["height"] // 2
                for qt_screen in qt_screens:
                    geo = qt_screen.geometry()
                    if (geo.x() <= center_x < geo.x() + geo.width() and
                            geo.y() <= center_y < geo.y() + geo.height()):
                        dpi_scale = qt_screen.devicePixelRatio()
                        break

            grab = sct.grab(mon)
            display_w, display_h = grab.width, grab.height

            img = Image.frombytes("RGB", (display_w, display_h), grab.rgb)

            # Normalize to the closest supported aspect-ratio resolution so the
            # model always sees a predictable coordinate space.
            target_w, target_h = _choose_target_resolution(display_w, display_h)
            img = img.resize((target_w, target_h), Image.LANCZOS)

            scale_x = target_w / display_w
            scale_y = target_h / display_h
            image_w, image_h = img.size

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=_JPEG_QUALITY)
            jpeg_bytes = buf.getvalue()

            label = compose_screen_label(screen_index, total, is_cursor)

            results.append(
                ScreenshotImage(
                    jpeg_bytes=jpeg_bytes,
                    label=label,
                    is_cursor_screen=is_cursor,
                    display_width_px=display_w,
                    display_height_px=display_h,
                    image_width_px=image_w,
                    image_height_px=image_h,
                    scale_x=scale_x,
                    scale_y=scale_y,
                    monitor_left=mon["left"],
                    monitor_top=mon["top"],
                    dpi_scale=dpi_scale,
                )
            )

    return results
