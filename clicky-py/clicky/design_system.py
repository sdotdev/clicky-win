"""Design system tokens for ClickyWin.

A cohesive premium dark-glass visual language: deep neutral backgrounds, a
vibrant electric-to-violet accent ramp, neon HUD colours, and helpers for
particle / firework / confetti palettes used by the viral effect overlays.

All token names that earlier code referenced are preserved; values have been
refined and a large set of new tokens added on top.
"""

from __future__ import annotations

import colorsys
import math


class DS:
    class Colors:
        # ---- Backgrounds (deep glass) -------------------------------------
        bg_deep = "#0b0d12"        # near-black base, slight blue
        panel_bg = "#12141c"       # primary panel
        panel_bg_alt = "#171a24"   # raised panel
        surface = "#1d2130"        # control surface
        surface_hover = "#262b3d"  # hovered control
        glass_tint = "#1a1e2b"     # translucent glass fill (use with alpha)

        # ---- Text ---------------------------------------------------------
        text_primary = "#eef1f8"
        text_secondary = "#9aa3b8"
        text_muted = "#5d6577"
        text_white = "#ffffff"

        # ---- Accent ramp (electric blue → violet) -------------------------
        accent_blue = "#4a9eff"
        accent_blue_bright = "#6cb4ff"
        accent_indigo = "#6d6cff"
        accent_violet = "#a855f7"
        accent_magenta = "#ec4899"
        accent_cyan = "#22d3ee"
        accent_green = "#4ade80"
        accent_amber = "#f59e0b"
        accent_pink = "#ff5d8f"
        accent_orange = "#ff7a45"
        accent_lime = "#a3e635"

        # ---- Neon (HUD / scan) -------------------------------------------
        neon_cyan = "#00f0ff"
        neon_blue = "#3b82f6"
        neon_violet = "#b14dff"
        neon_pink = "#ff3df0"
        neon_lime = "#3dffa3"

        # ---- Waveform / transcript ---------------------------------------
        waveform_bar = "#4a9eff"
        interim_text = "#9aa3b8"
        final_text = "#ffffff"

        # ---- Status banner ------------------------------------------------
        error_bg = "#3a0e16"
        warning_bg = "#3a2a0c"
        info_bg = "#0e2236"
        error_red = "#ff5a65"

        # ---- Companion state colours -------------------------------------
        companion_idle = "#4a9eff"
        companion_listening = "#4a9eff"
        companion_processing = "#f5a623"
        companion_responding = "#34d399"
        companion_error = "#ef4444"

        # ---- Borders ------------------------------------------------------
        border = "#2a2f40"
        border_bright = "#3a4156"
        border_strong = "#4a5169"

        # ---- Light mode (legacy output/input panels still reference these) -
        # Re-themed to dark glass so the floating panels match the new look.
        light_bg = "#141826"
        light_surface = "#1f2436"
        light_border = "#2c3247"
        light_text = "#eef1f8"
        light_text_secondary = "#9aa3b8"

    class Gradients:
        # (start_hex, end_hex) pairs for linear sweeps
        accent = ("#4a9eff", "#a855f7")
        accent_cool = ("#22d3ee", "#4a9eff")
        accent_hot = ("#ec4899", "#a855f7")
        power = ("#ffcc00", "#ff3df0")
        success = ("#4ade80", "#22d3ee")

    class CornerRadius:
        pill = 999
        large = 18
        medium = 12
        small = 8
        xs = 4

    class Spacing:
        xs = 4
        sm = 8
        md = 12
        lg = 16
        xl = 24

    class Fonts:
        family_ui = "Segoe UI"
        family_mono = "Cascadia Code, Consolas, monospace"
        size_xs = 11
        size_sm = 12
        size_md = 14
        size_lg = 16
        size_xl = 22

    # ---- Effect palettes --------------------------------------------------
    POWER_PALETTE = ["#ffd166", "#ff7a45", "#ff3df0", "#b14dff", "#4a9eff", "#22d3ee"]
    FIREWORK_PALETTE = ["#ff5d8f", "#ffd166", "#4ade80", "#22d3ee", "#a855f7", "#ff7a45", "#6cb4ff"]
    CONFETTI_PALETTE = [
        "#ff5d8f", "#ffd166", "#4ade80", "#22d3ee",
        "#a855f7", "#ff7a45", "#6cb4ff", "#ffffff",
    ]
    SCAN_PALETTE = ["#00f0ff", "#3dffa3", "#b14dff", "#ff3df0", "#6cb4ff"]


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert ``#rrggbb`` to an ``(r, g, b)`` int tuple."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def lerp_color(a: str, b: str, t: float) -> tuple[int, int, int]:
    """Linearly interpolate between two hex colours, returning an RGB tuple.

    ``t`` is clamped to [0, 1]; 0 returns ``a``, 1 returns ``b``.
    """
    t = max(0.0, min(1.0, t))
    ar, ag, ab = hex_to_rgb(a)
    br, bg, bb = hex_to_rgb(b)
    return (
        int(ar + (br - ar) * t),
        int(ag + (bg - ag) * t),
        int(ab + (bb - ab) * t),
    )


def hsv_color(hue: float, sat: float = 0.85, val: float = 1.0) -> tuple[int, int, int]:
    """Return an RGB tuple for an HSV triple. ``hue`` wraps modulo 1.0."""
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, sat, val)
    return int(r * 255), int(g * 255), int(b * 255)


def ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def ease_out_back(t: float, overshoot: float = 1.70158) -> float:
    c1 = overshoot
    c3 = c1 + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


def ease_in_out_sine(t: float) -> float:
    return -(math.cos(math.pi * t) - 1.0) / 2.0
