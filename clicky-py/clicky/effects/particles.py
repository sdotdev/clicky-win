"""Pure particle physics for the viral effect overlays.

Zero Qt / network dependencies so the simulation can be unit-tested in
isolation. Widgets own a list of :class:`Particle` and call :meth:`step`
each frame, then render whatever is still alive.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class Particle:
    """A single physics-driven particle.

    Positions/velocities are in pixels and pixels-per-second. ``life`` counts
    down from ``max_life`` (seconds); the particle is dead once it reaches 0.
    """

    x: float
    y: float
    vx: float
    vy: float
    max_life: float
    color: tuple[int, int, int]
    size: float = 3.0
    life: float = field(default=-1.0)
    gravity: float = 900.0       # px/s² downward
    drag: float = 0.86           # velocity retained per second (applied via dt)
    shrink: float = 1.0          # size multiplier applied per second
    twinkle: float = 0.0         # 0 = steady, >0 = sparkle flicker amount

    def __post_init__(self) -> None:
        if self.life < 0.0:
            self.life = self.max_life

    def step(self, dt: float) -> bool:
        """Advance one frame. Returns ``True`` while the particle is alive."""
        # Exponential drag that is correct for arbitrary dt.
        damp = self.drag ** dt
        self.vx *= damp
        self.vy *= damp
        self.vy += self.gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.size *= self.shrink ** dt
        self.life -= dt
        return self.life > 0.0

    @property
    def alpha(self) -> float:
        """0..1 opacity that fades as the particle ages, with optional twinkle."""
        base = max(0.0, min(1.0, self.life / self.max_life)) if self.max_life else 0.0
        if self.twinkle > 0.0:
            flicker = 1.0 - self.twinkle * (0.5 + 0.5 * math.sin(self.life * 40.0))
            base *= max(0.0, flicker)
        return base


def spawn_burst(
    x: float,
    y: float,
    count: int,
    palette: list[str],
    *,
    speed: float = 520.0,
    speed_jitter: float = 0.55,
    life: float = 0.9,
    life_jitter: float = 0.4,
    size: float = 4.0,
    gravity: float = 900.0,
    drag: float = 0.16,
    rng: random.Random | None = None,
) -> list[Particle]:
    """Radial explosion of ``count`` particles emanating from ``(x, y)``.

    ``palette`` is a list of ``#rrggbb`` strings; colours are picked at random.
    Returns the new particles (caller appends them to its live list).
    """
    r = rng or random
    from clicky.design_system import hex_to_rgb

    out: list[Particle] = []
    for _ in range(count):
        ang = r.uniform(0.0, 2.0 * math.pi)
        spd = speed * (1.0 - speed_jitter * r.random())
        out.append(
            Particle(
                x=x,
                y=y,
                vx=math.cos(ang) * spd,
                vy=math.sin(ang) * spd,
                max_life=life * (1.0 - life_jitter * r.random()),
                color=hex_to_rgb(r.choice(palette)),
                size=size * r.uniform(0.6, 1.3),
                gravity=gravity,
                drag=drag,
                shrink=0.55,
                twinkle=r.uniform(0.0, 0.5),
            )
        )
    return out


def spawn_trail_spark(
    x: float,
    y: float,
    palette: list[str],
    *,
    drift: float = 90.0,
    life: float = 0.55,
    size: float = 3.2,
    rng: random.Random | None = None,
) -> Particle:
    """A single soft spark that drifts up and out — used for cursor trails."""
    r = rng or random
    from clicky.design_system import hex_to_rgb

    ang = r.uniform(0.0, 2.0 * math.pi)
    return Particle(
        x=x + r.uniform(-4, 4),
        y=y + r.uniform(-4, 4),
        vx=math.cos(ang) * drift,
        vy=math.sin(ang) * drift - 40.0,
        max_life=life * r.uniform(0.6, 1.0),
        color=hex_to_rgb(r.choice(palette)),
        size=size * r.uniform(0.5, 1.1),
        gravity=60.0,
        drag=0.10,
        shrink=0.5,
        twinkle=r.uniform(0.0, 0.6),
    )


def step_all(particles: list[Particle], dt: float) -> list[Particle]:
    """Advance every particle by ``dt`` and return only the survivors."""
    return [p for p in particles if p.step(dt)]
