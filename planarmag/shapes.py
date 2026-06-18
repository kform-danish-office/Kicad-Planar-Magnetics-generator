"""Winding contour shapes.

A :class:`Shape` defines the outer contour a winding follows and how it shrinks
turn-by-turn.  The key method is :meth:`Shape.point_at(theta, inset)`: the point
on the contour at ray angle ``theta``, with the contour shrunk inward (offset)
by ``inset`` millimetres.  ``inset = 0`` is the outermost turn; larger insets
spiral inward toward the centre.

Two shapes are provided:

* :class:`Circle`        - round windings (rod / pot / RM / round-leg cores).
* :class:`RoundedRect`   - racetrack / "obround" windings that hug a rectangular
  centre leg (planar E / ELP cores).  A square or rounded rectangle is just a
  ``RoundedRect`` with the appropriate corner radius.

Because both terminals and inter-layer vias are placed via ``point_at`` with the
same ``(theta, inset)``, the geometry of every layer lines up automatically.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .geometry import Point, polar

Center = tuple[float, float]


class Shape:
    """Base class - subclasses implement the contour geometry."""

    center: Center = (0.0, 0.0)

    def point_at(self, theta: float, inset: float) -> Point:  # pragma: no cover
        raise NotImplementedError

    def max_inset(self) -> float:  # pragma: no cover
        raise NotImplementedError

    def bbox(self) -> tuple[float, float, float, float]:  # pragma: no cover
        raise NotImplementedError

    def mean_outer_diameter(self) -> float:  # pragma: no cover
        raise NotImplementedError

    def mean_inner_diameter(self, inset: float) -> float:  # pragma: no cover
        raise NotImplementedError

    def outward_unit(self, theta: float, inset: float = 0.0) -> Point:
        """Unit vector pointing radially outward at ``theta`` (for lead-outs)."""
        cx, cy = self.center
        px, py = self.point_at(theta, inset)
        dx, dy = px - cx, py - cy
        n = math.hypot(dx, dy) or 1.0
        return (dx / n, dy / n)


@dataclass
class Circle(Shape):
    radius: float
    center: Center = (0.0, 0.0)

    def point_at(self, theta: float, inset: float) -> Point:
        return polar(self.radius - inset, theta, self.center)

    def grown(self, d: float) -> "Circle":
        """Return a copy expanded outward by ``d`` mm on every side."""
        return Circle(self.radius + d, self.center)

    def max_inset(self) -> float:
        return self.radius

    def bbox(self) -> tuple[float, float, float, float]:
        cx, cy = self.center
        r = self.radius
        return (cx - r, cy - r, cx + r, cy + r)

    def mean_outer_diameter(self) -> float:
        return 2.0 * self.radius

    def mean_inner_diameter(self, inset: float) -> float:
        return 2.0 * (self.radius - inset)


def _rrect_sdf(px: float, py: float, hw: float, hh: float, r: float) -> float:
    """Signed distance from point to a rounded rectangle (negative inside)."""
    qx = abs(px) - hw + r
    qy = abs(py) - hh + r
    return min(max(qx, qy), 0.0) + math.hypot(max(qx, 0.0), max(qy, 0.0)) - r


def _ray_hit(hw: float, hh: float, r: float, theta: float) -> float:
    """Distance from the origin to the rounded-rect boundary along ``theta``."""
    ux, uy = math.cos(theta), math.sin(theta)
    lo, hi = 0.0, math.hypot(hw, hh) + r + 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _rrect_sdf(mid * ux, mid * uy, hw, hh, r) < 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@dataclass
class RoundedRect(Shape):
    """Rounded rectangle / racetrack with half-extents ``half_w`` x ``half_h``."""

    half_w: float
    half_h: float
    corner: float = 0.0
    center: Center = (0.0, 0.0)

    def __post_init__(self) -> None:
        self.corner = max(0.0, min(self.corner, min(self.half_w, self.half_h)))

    def point_at(self, theta: float, inset: float) -> Point:
        hw = self.half_w - inset
        hh = self.half_h - inset
        if hw <= 1e-6 or hh <= 1e-6:
            raise ValueError("RoundedRect inset exceeds half-size (winding collapses)")
        rc = max(0.0, self.corner - inset)
        d = _ray_hit(hw, hh, rc, theta)
        cx, cy = self.center
        return (cx + d * math.cos(theta), cy + d * math.sin(theta))

    def grown(self, d: float) -> "RoundedRect":
        """Return a copy expanded outward by ``d`` mm on every side."""
        return RoundedRect(self.half_w + d, self.half_h + d, self.corner + d, self.center)

    def max_inset(self) -> float:
        return min(self.half_w, self.half_h)

    def bbox(self) -> tuple[float, float, float, float]:
        cx, cy = self.center
        return (cx - self.half_w, cy - self.half_h, cx + self.half_w, cy + self.half_h)

    def mean_outer_diameter(self) -> float:
        return self.half_w + self.half_h

    def mean_inner_diameter(self, inset: float) -> float:
        return (self.half_w - inset) + (self.half_h - inset)
