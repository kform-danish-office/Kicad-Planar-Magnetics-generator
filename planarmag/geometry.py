"""Spiral / polygon geometry for planar magnetic windings.

All coordinates are in millimetres, which is the native unit of KiCad board
files.  Angles are in radians, measured counter-clockwise from the +X axis,
matching the usual maths convention.  (Note: KiCad's screen Y axis points
*down*, but a winding is symmetric enough that we don't worry about it here -
"counter-clockwise in maths" simply looks clockwise on screen.)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float]


@dataclass(frozen=True)
class Endpoint:
    """One end of a spiral arm: its radius, angle and resulting xy position."""

    radius: float
    angle: float
    xy: Point


def polar(radius: float, angle: float, center: Point = (0.0, 0.0)) -> Point:
    """Return the cartesian point at (radius, angle) about ``center``."""
    cx, cy = center
    return (cx + radius * math.cos(angle), cy + radius * math.sin(angle))


def polygon_spiral(
    *,
    r_start: float,
    r_end: float,
    start_angle: float,
    sweep: float,
    sides: int,
    center: Point = (0.0, 0.0),
) -> list[Point]:
    """Generate a polygonal (or, for large ``sides``, near-circular) spiral.

    The radius varies linearly with angle from ``r_start`` to ``r_end`` while
    the angle sweeps ``sweep`` radians (positive = counter-clockwise) starting
    at ``start_angle``.  Vertices are placed on the ``sides`` regular angular
    divisions so that ``sides=4`` gives a square spiral, ``8`` an octagon and
    e.g. ``64`` a smooth circle.  The exact endpoints are always included.

    Returns an ordered list of points tracing the spiral.
    """
    if sides < 3:
        raise ValueError("sides must be >= 3 (use a large value for circular)")
    if sweep == 0:
        return [polar(r_start, start_angle, center)]

    direction = 1.0 if sweep > 0 else -1.0
    total = abs(sweep)
    step = 2.0 * math.pi / sides

    # Angular offsets (relative to start) at which to drop a vertex: every
    # polygon division, plus the exact final point.
    offsets: list[float] = []
    a = 0.0
    while a < total - 1e-12:
        offsets.append(a)
        a += step
    offsets.append(total)

    pts: list[Point] = []
    for off in offsets:
        frac = off / total
        radius = r_start + (r_end - r_start) * frac
        angle = start_angle + direction * off
        pts.append(polar(radius, angle, center))
    return pts


def shape_spiral(
    shape,
    *,
    start_angle: float,
    sweep: float,
    inset_start: float,
    inset_end: float,
    sides: int,
) -> list[Point]:
    """Spiral that follows ``shape`` while the inset ramps ``inset_start->inset_end``.

    ``shape`` is any :class:`planarmag.shapes.Shape`.  The ray angle sweeps
    ``sweep`` radians from ``start_angle`` (positive = counter-clockwise) while
    the contour is offset inward from ``inset_start`` to ``inset_end``, sampled
    on ``sides`` angular divisions per full turn (plus the exact endpoints).
    """
    if sides < 3:
        raise ValueError("sides must be >= 3")
    if sweep == 0:
        return [shape.point_at(start_angle, inset_start)]

    direction = 1.0 if sweep > 0 else -1.0
    total = abs(sweep)
    step = 2.0 * math.pi / sides

    offsets: list[float] = []
    a = 0.0
    while a < total - 1e-12:
        offsets.append(a)
        a += step
    offsets.append(total)

    pts: list[Point] = []
    for off in offsets:
        frac = off / total
        inset = inset_start + (inset_end - inset_start) * frac
        angle = start_angle + direction * off
        pts.append(shape.point_at(angle, inset))
    return pts


def polyline_length(pts: list[Point]) -> float:
    """Total length of a polyline in millimetres."""
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def bbox(pts: list[Point]) -> tuple[float, float, float, float]:
    """Axis-aligned bounding box as ``(xmin, ymin, xmax, ymax)``."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))
