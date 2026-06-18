"""Convert a wire-wound transformer/inductor spec into a planar realisation.

Given a conventional design (turns ratio + the copper actually used, as AWG or a
cross-section), this finds planar options that carry the same copper: it trades
**core size** against **parallel copper** (more layers / paralleled turns).

The model, per winding with ``N`` turns needing copper area ``A_req``:

* turns are series-stacked over ``series_layers`` layers, ``N/series_layers`` per
  layer; the trace width that fits the core's radial window is
  ``w = window/turns_per_layer - clearance``;
* the copper area of one such trace is ``w * t_copper``; to reach ``A_req`` you
  parallel ``P = ceil(A_req / (w * t_copper))`` copies;
* total layers for the winding = ``series_layers * P``.

For each candidate core it picks the realisation with the fewest layers (subject
to a minimum trace width), then ranks cores.  A bigger core widens the window, so
needs less paralleling - exactly the trade the user asked to see.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .core import CORES, Core
from .shapes import Shape
from .windings import OZ_TO_M, _RHO_CU

# Bare solid-copper cross-section (mm^2) by AWG.
AWG_AREA_MM2 = {
    8: 8.367, 9: 6.631, 10: 5.261, 11: 4.172, 12: 3.309, 13: 2.624,
    14: 2.081, 15: 1.650, 16: 1.309, 17: 1.038, 18: 0.823, 19: 0.653,
    20: 0.518, 21: 0.410, 22: 0.326, 23: 0.258, 24: 0.205, 25: 0.162,
    26: 0.129, 27: 0.102, 28: 0.0810, 29: 0.0642, 30: 0.0509, 31: 0.0404,
    32: 0.0320, 33: 0.0254, 34: 0.0201, 35: 0.0160, 36: 0.0127, 37: 0.0100,
    38: 0.00797, 39: 0.00632, 40: 0.00501,
}


def awg_area(awg: int, strands: int = 1) -> float:
    """Copper cross-section (mm^2) of ``strands`` parallel wires of ``awg``."""
    if awg not in AWG_AREA_MM2:
        raise ValueError(f"AWG {awg} not in table ({min(AWG_AREA_MM2)}..{max(AWG_AREA_MM2)})")
    return AWG_AREA_MM2[awg] * strands


@dataclass
class Winding:
    """One wound winding: turns + the copper it uses."""

    turns: int
    awg: int | None = None
    strands: int = 1
    area_mm2: float | None = None   # explicit copper area instead of AWG
    current_a: float | None = None  # optional RMS current (for J reporting)

    def required_area(self) -> float:
        if self.area_mm2 is not None:
            return self.area_mm2
        if self.awg is not None:
            return awg_area(self.awg, self.strands)
        raise ValueError("winding needs awg or area_mm2")


@dataclass
class WireWound:
    """A wire-wound transformer (or inductor: omit secondary) to convert."""

    primary: Winding
    secondary: Winding | None = None
    frequency_hz: float | None = None

    @property
    def ratio(self) -> float:
        if self.secondary is None:
            return float("nan")
        return self.primary.turns / self.secondary.turns


def _perimeter(shape: Shape, n: int = 256) -> float:
    pts = [shape.point_at(2 * math.pi * i / n, 0.0) for i in range(n)]
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:] + pts[:1]))


@dataclass
class WindingPlan:
    winding: str            # "primary"/"secondary"
    turns: int
    series_layers: int
    parallel: int
    turns_per_layer: int
    trace_width: float
    copper_oz: float
    copper_area: float      # achieved (mm^2)
    required_area: float
    total_layers: int
    dcr_mohm: float
    feasible: bool

    def line(self) -> str:
        flag = "" if self.feasible else "  [INFEASIBLE]"
        return (f"{self.winding:<9} {self.turns:>3}T  "
                f"{self.series_layers}series x {self.parallel}parallel "
                f"= {self.total_layers:>2} layers  "
                f"w={self.trace_width:.2f}mm {self.copper_oz:g}oz  "
                f"Cu {self.copper_area:.3f}/{self.required_area:.3f}mm2  "
                f"~{self.dcr_mohm:.1f} mOhm{flag}")


def _solve_winding(core: Core, name: str, turns: int, req_area: float,
                   copper_oz: float, clearance: float, min_trace: float,
                   max_series: int) -> WindingPlan:
    """Fewest-layer planar realisation of one winding on ``core``."""
    t_cu = copper_oz * OZ_TO_M * 1e3            # copper thickness in mm
    usable = core.window_radial - core.core_clearance   # radial space for copper
    best: WindingPlan | None = None
    for series in range(1, max_series + 1):
        tpl = math.ceil(turns / series)
        w = usable / tpl - clearance
        if w < min_trace:
            continue
        area_per = w * t_cu
        parallel = max(1, math.ceil(req_area / area_per))
        total = series * parallel
        buildup = tpl * (w + clearance)
        mid = core.inner_shape().grown(buildup / 2.0)
        mean_turn_mm = _perimeter(mid)
        len_m = turns * mean_turn_mm / 1000.0
        area_m2 = (w / 1000.0) * (copper_oz * OZ_TO_M) * parallel
        dcr = _RHO_CU * len_m / area_m2 * 1e3
        plan = WindingPlan(name, turns, series, parallel, tpl, w, copper_oz,
                           area_per * parallel, req_area, total, dcr, True)
        if best is None or plan.total_layers < best.total_layers or (
                plan.total_layers == best.total_layers and w > best.trace_width):
            best = plan
    if best is None:  # window can't even fit one turn at min trace
        return WindingPlan(name, turns, 0, 0, 0, min_trace, copper_oz, 0.0,
                           req_area, 0, float("inf"), False)
    return best


@dataclass
class PlanarDesign:
    core_name: str
    primary: WindingPlan
    secondary: WindingPlan | None
    copper_oz: float

    @property
    def total_layers(self) -> int:
        n = self.primary.total_layers
        if self.secondary:
            n += self.secondary.total_layers
        return n

    @property
    def feasible(self) -> bool:
        return self.primary.feasible and (self.secondary is None or self.secondary.feasible)

    def boards(self, layers_per_board: int) -> int:
        return math.ceil(self.total_layers / layers_per_board)

    def report(self, layers_per_board: int = 4) -> str:
        out = [f"core {self.core_name}: {self.total_layers} layers total"
               f" -> {self.boards(layers_per_board)} x {layers_per_board}-layer board(s)"
               f"   ({self.copper_oz:g} oz)"]
        out.append("  " + self.primary.line())
        if self.secondary:
            out.append("  " + self.secondary.line())
        return "\n".join(out)


def convert(spec: WireWound, *, cores: list[str] | None = None,
            copper_oz: tuple[float, ...] = (1.0, 2.0), clearance: float = 0.2,
            min_trace: float = 0.15, max_series_layers: int = 12,
            layers_per_board: int = 4, max_results: int = 6) -> list[PlanarDesign]:
    """Survey the core library for planar realisations, ranked best-first.

    "Best" = feasible, fewest total copper layers, then smallest core.  Returns
    up to ``max_results`` :class:`PlanarDesign` s.
    """
    names = cores if cores is not None else list(CORES)
    pri_area = spec.primary.required_area()
    sec_area = spec.secondary.required_area() if spec.secondary else None

    designs: list[PlanarDesign] = []
    for cname in names:
        core = CORES[cname]
        for oz in copper_oz:
            p = _solve_winding(core, "primary", spec.primary.turns, pri_area,
                               oz, clearance, min_trace, max_series_layers)
            s = None
            if spec.secondary:
                s = _solve_winding(core, "secondary", spec.secondary.turns,
                                   sec_area, oz, clearance, min_trace, max_series_layers)
            designs.append(PlanarDesign(cname, p, s, oz))

    # core "size" tiebreak by footprint area (or Ae)
    def size(d: PlanarDesign) -> float:
        c = CORES[d.core_name]
        return (c.footprint[0] * c.footprint[1]) if c.footprint else (c.Ae or 1e9)

    designs.sort(key=lambda d: (not d.feasible, d.total_layers, size(d)))
    return designs[:max_results]


def convert_report(spec: WireWound, *, layers_per_board: int = 4, **kw) -> str:
    """Human-readable ranked conversion report."""
    designs = convert(spec, layers_per_board=layers_per_board, **kw)
    head = [f"Wire-wound -> planar conversion",
            f"  primary  : {spec.primary.turns}T, "
            f"{spec.primary.required_area():.3f} mm2 copper"]
    if spec.secondary:
        head.append(f"  secondary: {spec.secondary.turns}T, "
                    f"{spec.secondary.required_area():.3f} mm2 copper "
                    f"(ratio {spec.ratio:.2f})")
    head.append("")
    head.append("Ranked options (fewest layers first):")
    body = [d.report(layers_per_board) for d in designs]
    return "\n".join(head + body)
