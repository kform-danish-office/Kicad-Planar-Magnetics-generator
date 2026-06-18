"""Multi-layer planar windings (coils) built on contour shapes.

A :class:`Coil` is a single electrical winding that snakes through one or more
copper layers, following a :class:`~planarmag.shapes.Shape` (circular or
rectangular/racetrack).  Each layer carries ``turns`` turns; consecutive layers
are joined by a via and wound so the current circulates the *same* way on every
layer, so the layer fluxes add (series-stacked coil).

Endpoint placement
------------------
The two terminals and every interlayer via get a *distinct* ray angle, so they
never overlap for any layer count.  Terminal angles can be pinned via
``terminal_angles`` - this is what lets a winding be split across several boards
that connect through shared vertical pin columns (see ``devices.make_*_stack``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .geometry import Point, shape_spiral, polyline_length
from .kicad import Board
from .shapes import Circle, Shape

_RHO_CU = 1.68e-8          # copper resistivity, ohm-metre
OZ_TO_M = 34.79e-6         # 1 oz/ft^2 copper thickness, metres


@dataclass
class Terminal:
    """An accessible end of a coil."""

    name: str
    xy: Point
    angle: float
    inset: float
    rail: str  # "outer" or "inner"
    layer_index: int
    net: int


@dataclass
class CoilResult:
    terminals: list[Terminal]
    conductor_length_mm: float
    turns_total: float
    inset_total: float
    shape: Shape

    def resistance_mohm(self, trace_width_mm: float, copper_oz: float = 1.0) -> float:
        """Rough DC resistance in milliohms (ignores temperature & vias)."""
        length_m = self.conductor_length_mm / 1000.0
        area_m2 = (trace_width_mm / 1000.0) * (copper_oz * OZ_TO_M)
        return _RHO_CU * length_m / area_m2 * 1e3


@dataclass
class Coil:
    """A single winding threaded through ``layer_indices`` (outermost order)."""

    turns: float
    trace_width: float
    clearance: float
    layer_indices: list[int]
    net: int
    shape: Shape | None = None
    r_outer: float | None = None          # convenience: builds a Circle
    name: str = "L"
    sides: int = 64
    inset_total: float | None = None
    terminal_angles: tuple[float, float] | None = None
    stagger_deg: float = 18.0
    via_size: float = 0.6
    via_drill: float = 0.3

    def __post_init__(self) -> None:
        if self.shape is None:
            if self.r_outer is None:
                raise ValueError("Coil needs either a shape or r_outer")
            self.shape = Circle(self.r_outer)

    @property
    def pitch(self) -> float:
        return self.trace_width + self.clearance

    def _total_inset(self) -> float:
        inset = self.turns * self.pitch if self.inset_total is None else self.inset_total
        limit = self.shape.max_inset() - self.trace_width
        if inset >= limit:
            raise ValueError(
                f"coil '{self.name}': winding build-up {inset:.2f} mm exceeds the "
                f"available {limit:.2f} mm - reduce turns/width/clearance or "
                f"enlarge the contour"
            )
        return inset

    def _endpoint_angles(self) -> list[float]:
        n = len(self.layer_indices) + 1
        delta = math.radians(self.stagger_deg)
        angles = [0.0] * n

        if self.terminal_angles is not None:
            angles[0], angles[-1] = self.terminal_angles
            mids = list(range(1, n - 1))
            # spread internal vias around the far side (pi) of the terminals
            for group in ([k for k in mids if k % 2 == 0],
                          [k for k in mids if k % 2 == 1]):
                m = len(group)
                for j, k in enumerate(group):
                    angles[k] = math.pi + (j - (m - 1) / 2.0) * delta
            return angles

        outer_idx = [k for k in range(n) if k % 2 == 0]
        inner_idx = [k for k in range(n) if k % 2 == 1]
        for base, group in ((0.0, outer_idx), (math.pi, inner_idx)):
            m = len(group)
            for j, k in enumerate(group):
                angles[k] = base + (j - (m - 1) / 2.0) * delta
        return angles

    def build(self, board: Board) -> CoilResult:
        shape = self.shape
        inset_total = self._total_inset()
        angles = self._endpoint_angles()
        target_sweep = self.turns * 2.0 * math.pi
        total_len = 0.0

        # spiral arm on each layer ------------------------------------------
        for i, layer in enumerate(self.layer_indices):
            inward = (i % 2 == 0)
            a_start, a_end = angles[i], angles[i + 1]
            raw = a_end - a_start
            k = round((target_sweep - raw) / (2.0 * math.pi))
            sweep = raw + k * 2.0 * math.pi
            if sweep <= 0:
                sweep += 2.0 * math.pi

            in0, in1 = (0.0, inset_total) if inward else (inset_total, 0.0)
            pts = shape_spiral(
                shape, start_angle=a_start, sweep=sweep,
                inset_start=in0, inset_end=in1, sides=self.sides,
            )
            board.add_track(pts, self.trace_width, layer, self.net)
            total_len += polyline_length(pts)

        # vias joining consecutive layers -----------------------------------
        for k in range(1, len(self.layer_indices)):
            inset = 0.0 if (k % 2 == 0) else inset_total
            at = shape.point_at(angles[k], inset)
            board.add_via(
                at, self.net, size=self.via_size, drill=self.via_drill,
                from_layer=self.layer_indices[k - 1], to_layer=self.layer_indices[k],
            )

        # terminals ----------------------------------------------------------
        terminals: list[Terminal] = []
        last = len(self.layer_indices)
        for label, idx, layer in (("start", 0, self.layer_indices[0]),
                                   ("end", last, self.layer_indices[-1])):
            rail_outer = (idx % 2 == 0)
            inset = 0.0 if rail_outer else inset_total
            terminals.append(
                Terminal(
                    name=f"{self.name}.{label}",
                    xy=shape.point_at(angles[idx], inset),
                    angle=angles[idx],
                    inset=inset,
                    rail="outer" if rail_outer else "inner",
                    layer_index=layer,
                    net=self.net,
                )
            )

        return CoilResult(
            terminals=terminals,
            conductor_length_mm=total_len,
            turns_total=self.turns * len(self.layer_indices),
            inset_total=inset_total,
            shape=shape,
        )
