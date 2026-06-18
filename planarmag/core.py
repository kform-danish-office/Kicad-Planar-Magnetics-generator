"""Magnetic cores: multi-leg geometry + the data library.

A :class:`Core` is a set of :class:`Leg` s (each with its own ``(x, y)``
position and cross-section) plus the winding-window width and the effective
magnetic parameters.  You wind around the leg flagged ``wound``; the board gets
a cut-out for every leg flagged ``cutout``.

Single-centre-leg cores: use :meth:`Core.round_leg` / :meth:`Core.rect_leg`.
Multi-leg cores: pass a ``legs=[...]`` list, or start from a library part and
add legs.  Library data lives in :mod:`planarmag.core_data` (real Ferroxcube /
IEC-62317 planar-E dimensions; verify against the datasheet before fabricating).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .core_data import ALIASES, CORE_DATA
from .kicad import Board
from .shapes import Circle, RoundedRect, Shape

Point = tuple[float, float]


@dataclass
class Leg:
    """One core leg: a round or rectangular post at a given (x, y)."""

    shape: str = "rect"             # "round" or "rect"
    pos: Point = (0.0, 0.0)
    diameter: float | None = None   # round
    width: float | None = None      # rect, along X
    length: float | None = None     # rect, along Y
    name: str = "leg"
    wound: bool = False             # the winding wraps this leg
    cutout: bool = True             # draw a board cut-out for this leg

    def half_extents(self) -> tuple[float, float]:
        if self.shape == "round":
            r = self.diameter / 2.0
            return (r, r)
        return (self.width / 2.0, self.length / 2.0)

    def inner_contour(self, clearance: float, corner: float) -> Shape:
        """Contour the innermost turn follows: this leg grown by ``clearance``."""
        if self.shape == "round":
            return Circle(self.diameter / 2.0 + clearance, self.pos)
        return RoundedRect(self.width / 2.0 + clearance,
                           self.length / 2.0 + clearance,
                           corner + clearance, self.pos)

    def draw_cutout(self, board: Board, fit: float, corner: float) -> None:
        if self.shape == "round":
            board.add_circle(self.pos, self.diameter / 2.0 + fit)
        else:
            rr = RoundedRect(self.width / 2.0 + fit, self.length / 2.0 + fit,
                             corner, self.pos)
            board.add_polygon([rr.point_at(2 * math.pi * i / 96, 0.0) for i in range(96)])


@dataclass
class Core:
    name: str
    legs: list[Leg] = field(default_factory=list)
    window_radial: float = 6.0      # radial winding window (per side) (mm)
    window_height: float | None = None  # slot height the PCB stack fits in (mm)
    footprint: tuple[float, float] | None = None
    Ae: float | None = None         # effective area (mm^2)
    le: float | None = None         # effective length (mm)
    Ve: float | None = None         # effective volume (mm^3)
    core_clearance: float = 1.0     # copper-edge-to-leg gap (mm); keeps the inner
    #                                 turn well clear of the leg cut-out (DRC + creepage)
    leg_fit_clearance: float = 0.1  # cut-out oversize around the leg (mm)
    corner_radius: float = 0.6
    verified: bool = True
    note: str = ""
    source: str = ""

    # --- single-leg convenience constructors --------------------------------
    @classmethod
    def round_leg(cls, name: str, diameter: float, window_radial: float, **kw) -> "Core":
        leg = Leg(shape="round", diameter=diameter, name="center", wound=True, cutout=True)
        return cls(name, [leg], window_radial, **kw)

    @classmethod
    def rect_leg(cls, name: str, width: float, length: float,
                 window_radial: float, **kw) -> "Core":
        leg = Leg(shape="rect", width=width, length=length, name="center",
                  wound=True, cutout=True)
        return cls(name, [leg], window_radial, **kw)

    @classmethod
    def from_record(cls, rec: dict) -> "Core":
        cl = rec["center_leg"]
        legs = [Leg(shape=cl["shape"], pos=tuple(cl.get("pos", (0, 0))),
                    diameter=cl.get("diameter"), width=cl.get("width"),
                    length=cl.get("length"), name="center", wound=True, cutout=True)]
        for ol in rec.get("outer_legs", []):
            legs.append(Leg(shape=ol["shape"], pos=tuple(ol["pos"]),
                            diameter=ol.get("diameter"), width=ol.get("width"),
                            length=ol.get("length"), name="outer",
                            wound=False, cutout=False))
        fp = rec.get("footprint")
        return cls(rec["name"], legs, rec["window_radial"],
                   window_height=rec.get("window_height"),
                   footprint=tuple(fp) if fp else None,
                   Ae=rec.get("Ae"), le=rec.get("le"), Ve=rec.get("Ve"),
                   verified=rec.get("verified", True), source=rec.get("source", ""))

    # --- geometry -----------------------------------------------------------
    def add_leg(self, leg: Leg) -> "Core":
        self.legs.append(leg)
        return self

    def wound_leg(self) -> Leg:
        for leg in self.legs:
            if leg.wound:
                return leg
        return self.legs[0]

    def inner_shape(self, trace_width: float = 0.0) -> Shape:
        """Contour the innermost turn's *centreline* follows.

        Offsets the leg by ``core_clearance`` plus half the trace width, so the
        copper *edge* (not just the centreline) clears the leg by ``core_clearance``.
        """
        return self.wound_leg().inner_contour(
            self.core_clearance + trace_width / 2.0, self.corner_radius)

    def winding_shape(self, inset_total: float, trace_width: float = 0.0) -> Shape:
        """Outer winding contour: hugs the wound leg, grown out by the build-up."""
        return self.inner_shape(trace_width).grown(inset_total)

    def max_turns(self, trace_width: float, clearance: float) -> int:
        # leave the leg clearance and a full trace width (both inner & outer edges)
        usable = self.window_radial - self.core_clearance - trace_width
        return max(0, int(usable // (trace_width + clearance)))

    def draw_cutouts(self, board: Board) -> None:
        for leg in self.legs:
            if leg.cutout:
                leg.draw_cutout(board, self.leg_fit_clearance, self.corner_radius)

    def draw_footprint_ref(self, board: Board) -> None:
        """Draw the core's outline on Cmts.User as a reference (not the board edge).

        Planar-E windings legitimately extend past the core depth (end-turns), so
        the board edge is sized to the copper; this just shows where the core sits.
        """
        if self.footprint is None:
            return
        w, l = self.footprint
        board.add_polygon([(-w / 2, -l / 2), (w / 2, -l / 2),
                           (w / 2, l / 2), (-w / 2, l / 2)], layer="Cmts.User")

    def summary_lines(self) -> list[str]:
        leg = self.wound_leg()
        if leg.shape == "round":
            desc = f"round dia {leg.diameter} mm"
        else:
            desc = f"rect {leg.width} x {leg.length} mm"
        out = [f"core            : {self.name} ({len(self.legs)} legs, wound leg {desc})",
               f"window (radial) : {self.window_radial} mm  (height {self.window_height} mm)"]
        if self.Ae:
            out.append(f"Ae / le / Ve    : {self.Ae} mm2 / {self.le} mm / {self.Ve} mm3")
        if not self.verified:
            out.append("note            : NOMINAL - verify against datasheet!")
        return out


# --- library ----------------------------------------------------------------
CORES: dict[str, Core] = {rec["name"]: Core.from_record(rec) for rec in CORE_DATA}


def get_core(name: str) -> Core:
    """Look up a library core by name or alias (e.g. 'E32/6/20' or 'ELP32')."""
    key = name.strip()
    if key in CORES:
        return CORES[key]
    if key.upper() in ALIASES:
        return CORES[ALIASES[key.upper()]]
    # tolerate 'E32' for 'E32/6/20'
    for full in CORES:
        if full.split("/")[0].upper() == key.upper():
            return CORES[full]
    raise KeyError(
        f"unknown core '{name}'. Known: {', '.join(CORES)} "
        f"(aliases: {', '.join(ALIASES)}). Or build one with Core.rect_leg(...)."
    )


def list_cores() -> list[str]:
    return list(CORES)
