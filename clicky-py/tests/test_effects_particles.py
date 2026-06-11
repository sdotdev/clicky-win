"""Tests for the pure particle physics engine."""

import random

from clicky.effects.particles import (
    Particle,
    spawn_burst,
    spawn_trail_spark,
    step_all,
)


def test_particle_dies_after_max_life():
    p = Particle(x=0, y=0, vx=0, vy=0, max_life=0.25, color=(255, 0, 0), gravity=0)
    assert p.step(0.1) is True   # life 0.15
    assert p.step(0.1) is True   # life 0.05
    assert p.step(0.1) is False  # life now <= 0


def test_particle_alpha_fades_with_age():
    p = Particle(x=0, y=0, vx=0, vy=0, max_life=1.0, color=(1, 2, 3), gravity=0)
    assert p.alpha == 1.0
    p.step(0.5)
    assert 0.4 < p.alpha < 0.6


def test_gravity_pulls_particle_down():
    p = Particle(x=0, y=0, vx=0, vy=0, max_life=10.0, color=(1, 2, 3), gravity=1000, drag=1.0)
    p.step(0.1)
    assert p.y > 0  # moved downward
    assert p.vy > 0


def test_spawn_burst_count_and_origin():
    rng = random.Random(42)
    ps = spawn_burst(50, 60, 30, ["#ff0000", "#00ff00"], rng=rng)
    assert len(ps) == 30
    # All start at the burst origin.
    assert all(p.x == 50 and p.y == 60 for p in ps)
    # Colours come from the palette.
    assert all(p.color in {(255, 0, 0), (0, 255, 0)} for p in ps)


def test_spawn_burst_is_deterministic_with_seed():
    a = spawn_burst(0, 0, 10, ["#abcdef"], rng=random.Random(1))
    b = spawn_burst(0, 0, 10, ["#abcdef"], rng=random.Random(1))
    assert [(p.vx, p.vy) for p in a] == [(p.vx, p.vy) for p in b]


def test_step_all_removes_dead_particles():
    ps = [
        Particle(x=0, y=0, vx=0, vy=0, max_life=0.01, color=(1, 1, 1), gravity=0),
        Particle(x=0, y=0, vx=0, vy=0, max_life=10.0, color=(1, 1, 1), gravity=0),
    ]
    survivors = step_all(ps, 0.05)
    assert len(survivors) == 1
    assert survivors[0].max_life == 10.0


def test_trail_spark_has_short_life():
    p = spawn_trail_spark(5, 5, ["#ffffff"], rng=random.Random(0))
    assert p.max_life <= 0.6
    assert abs(p.x - 5) <= 4 and abs(p.y - 5) <= 4
