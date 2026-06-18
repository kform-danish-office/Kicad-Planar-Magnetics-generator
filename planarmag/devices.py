"""High-level planar magnetic devices.

Builders for spiral inductors and planar transformers, on a plain circular
outline or fitted to a magnetic :class:`~planarmag.core.Core`, plus
*multi-board* variants that split a winding across several stacked PCBs joined
by vertical pin columns.

Electrical figures (inductance via the Mohan current-sheet model, DC resistance)
are first-order estimates - see the README caveats.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .core import Core
from .geometry import Point
from .kicad import Board
from .materials import Material, get_material
from .physics import (
    StackLayer,
    al_value_nh,
    copper_thickness_mm,
    effective_permeability,
    flux_density_from_current,
    flux_density_from_voltage,
    leakage_inductance,
    magnetizing_inductance,
    saturation_check,
)
from .shapes import Circle, RoundedRect, Shape
from .windings import Coil, CoilResult, Terminal

MU0 = 4.0e-7 * math.pi

# Mohan/Niknejad current-sheet coefficients (c1..c4) by winding shape.
_SHEET_COEFFS = {
    "square": (1.27, 2.07, 0.18, 0.13),
    "hexagon": (1.09, 2.23, 0.00, 0.17),
    "octagon": (1.07, 2.29, 0.00, 0.19),
    "circle": (1.00, 2.46, 0.00, 0.20),
}


@dataclass
class Pin:
    """A through-board connection pin column."""

    drill: float = 0.7
    pad: float = 1.4
    gap: float = 2.0   # how far outside the winding the column sits (mm)


def _coeff_shape(shape: Shape, sides: int) -> str:
    if isinstance(shape, RoundedRect):
        return "square"
    if sides <= 4:
        return "square"
    if sides <= 6:
        return "hexagon"
    if sides <= 12:
        return "octagon"
    return "circle"


def spiral_inductance_h(*, n_turns: float, d_out_mm: float, d_in_mm: float,
                        coeff: str = "circle") -> float:
    """Estimate planar spiral inductance (henries) via the current-sheet model."""
    c1, c2, c3, c4 = _SHEET_COEFFS[coeff]
    d_avg = (d_out_mm + d_in_mm) / 2.0 * 1e-3
    rho = (d_out_mm - d_in_mm) / (d_out_mm + d_in_mm)
    if rho <= 0:
        return 0.0
    return (MU0 * n_turns**2 * d_avg * c1 / 2.0
            * (math.log(c2 / rho) + c3 * rho + c4 * rho**2))


def _inductance_of(result: CoilResult, n_total: float, sides: int) -> float:
    return spiral_inductance_h(
        n_turns=n_total,
        d_out_mm=result.shape.mean_outer_diameter(),
        d_in_mm=result.shape.mean_inner_diameter(result.inset_total),
        coeff=_coeff_shape(result.shape, sides),
    )


def _as_material(material) -> Material | None:
    if material is None:
        return None
    return get_material(material) if isinstance(material, str) else material


def _mlt_mm(shape: Shape, inset_total: float) -> float:
    """Mean length of a turn = perimeter of the mid-band contour."""
    n = 200
    pts = [shape.point_at(2 * math.pi * i / n, inset_total / 2.0) for i in range(n)]
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:] + pts[:1]))


def _core_inductance_lines(turns: float, core: Core, mat: Material,
                           gap_mm: float, current: float | None,
                           volt_s: float | None, temp_c: float) -> list[str]:
    """Magnetizing inductance + saturation lines for a cored winding."""
    if core.Ae is None or core.le is None:
        return [f"material        : {mat.name} (core has no Ae/le; using air-core est.)"]
    mu_e = effective_permeability(mat.mu_i, core.le, gap_mm)
    al = al_value_nh(core, mat, gap_mm)
    Lm = magnetizing_inductance(turns, core, mat, gap_mm)
    lines = [
        f"material        : {mat.name} (mu_i {mat.mu_i:g}), air gap {gap_mm:g} mm",
        f"mu_e / AL       : {mu_e:.0f} / {al:.1f} nH/N^2",
        f"L (magnetizing) : {Lm * 1e6:.2f} uH  ({turns:g} turns)",
    ]
    b = None
    if volt_s is not None:
        b = flux_density_from_voltage(volt_s, turns, core.Ae)
    elif current is not None:
        b = flux_density_from_current(Lm, current, turns, core.Ae)
    if b is not None:
        lines.append("saturation      : " + saturation_check(b, mat, temp_c).line())
    return lines


@dataclass
class DeviceSummary:
    name: str
    lines: list[str] = field(default_factory=list)
    boards: list[tuple[str, Board]] = field(default_factory=list)

    def __str__(self) -> str:
        return "\n".join([f"{self.name}:", *(f"  {ln}" for ln in self.lines)])

    def save_all(self, directory: str, *, stem: str | None = None) -> list[str]:
        """Save every board to ``directory``; returns the written paths."""
        import os

        os.makedirs(directory, exist_ok=True)
        if stem is None:
            stem = "".join(c if c.isalnum() else "_" for c in self.name).strip("_")
        paths = []
        for label, board in self.boards:
            path = os.path.join(directory, f"{stem}_{label}.kicad_pcb")
            board.save(path)
            paths.append(path)
        return paths


# --- shared helpers ---------------------------------------------------------
def _resolve(core: Core | None, shape: Shape | None, outer_diameter: float | None,
             turns: float, trace_width: float, clearance: float) -> tuple[Shape, float]:
    """Return (outer winding shape, total radial build-up) for one winding.

    With a core the winding *hugs the wound leg* and grows outward by the
    build-up (validated to fit the window).  Otherwise it is anchored to the
    given outer diameter / shape and grows inward.
    """
    inset_total = turns * (trace_width + clearance)
    if core is not None:
        needed = inset_total + core.core_clearance + trace_width   # both edges
        if needed > core.window_radial + 1e-9:
            raise ValueError(
                f"core '{core.name}': {turns:g} turns x "
                f"{trace_width + clearance:g} mm pitch + leg gap/edges = "
                f"{needed:.1f} mm exceeds the {core.window_radial} mm radial window "
                f"(max {core.max_turns(trace_width, clearance)} turns/layer)")
        return core.winding_shape(inset_total, trace_width), inset_total
    if shape is not None:
        return shape, inset_total
    if outer_diameter is not None:
        return Circle(outer_diameter / 2.0), inset_total
    raise ValueError("specify one of: core, shape, or outer_diameter")


def _lead_out(board: Board, shape: Shape, term: Terminal, *,
              length: float, width: float, label: str) -> None:
    if term.rail == "outer":
        ux, uy = shape.outward_unit(term.angle, term.inset)
        tip = (term.xy[0] + ux * length, term.xy[1] + uy * length)
        board.add_track([term.xy, tip], width, term.layer_index, term.net)
        board.add_via(tip, term.net, from_layer=0, to_layer=board.copper_layers - 1)
        board.add_text(label, (tip[0], tip[1] - 1.0), layer_index=0, size=0.9)
    else:
        board.add_via(term.xy, term.net, from_layer=0, to_layer=board.copper_layers - 1)
        board.add_text(label, (term.xy[0], term.xy[1] - 1.0), layer_index=0, size=0.9)


def _finish_outline(board: Board, core: Core | None, shape: Shape,
                    margin: float = 2.0) -> None:
    if core is not None:
        core.draw_cutouts(board)
        core.draw_footprint_ref(board)   # core outline on Cmts.User (reference)
    # the board edge always fits the actual copper (planar-E end-turns can extend
    # past the core depth), with a margin
    box = board.content_bbox()
    x0, y0, x1, y1 = box if box is not None else shape.bbox()
    board.set_outline(x0 - margin, y0 - margin, x1 + margin, y1 + margin)


# --- single-board inductor --------------------------------------------------
def make_inductor(*, turns: float = 8, copper_layers: int = 2,
                  trace_width: float = 0.4, clearance: float = 0.3,
                  sides: int = 64, copper_oz: float = 1.0, name: str = "L1",
                  core: Core | None = None, shape: Shape | None = None,
                  outer_diameter: float | None = 20.0,
                  material: "str | Material | None" = None, air_gap_mm: float = 0.0,
                  peak_current_a: float | None = None, temp_c: float = 100.0
                  ) -> tuple[Board, DeviceSummary]:
    """Series-stacked planar spiral inductor across all copper layers.

    Pass ``material`` (+ optional ``air_gap_mm``) to get the real magnetizing
    inductance and a saturation check instead of the air-core estimate.
    """
    if core is not None:
        outer_diameter = None
    mat = _as_material(material)
    shape, inset = _resolve(core, shape, outer_diameter, turns, trace_width, clearance)

    board = Board(copper_layers=copper_layers, title=f"Planar Inductor {name}")
    net = board.add_net(name)
    coil = Coil(turns=turns, trace_width=trace_width, clearance=clearance,
                layer_indices=list(range(copper_layers)), net=net, shape=shape,
                inset_total=inset, name=name, sides=sides)
    result = coil.build(board)

    for term, lbl in zip(result.terminals, (f"{name}-A", f"{name}-B")):
        _lead_out(board, shape, term, length=1.5, width=trace_width, label=lbl)
    _finish_outline(board, core, shape)

    n_total = turns * copper_layers
    lines = []
    if core is not None:
        lines += core.summary_lines()
        lines.append(f"max turns/layer : {core.max_turns(trace_width, clearance)} "
                     f"(using {turns:g})")
    lines += [
        f"copper layers   : {copper_layers}",
        f"turns/layer     : {turns:g}   total turns: {n_total:g}",
    ]
    if mat is not None and core is not None:
        lines += _core_inductance_lines(n_total, core, mat, air_gap_mm,
                                        peak_current_a, None, temp_c)
    else:
        L = _inductance_of(result, n_total, sides)
        lines.append(f"inductance      : {L * 1e6:.2f} uH (air-core est.)")
    lines += [
        f"DC resistance   : {result.resistance_mohm(trace_width, copper_oz):.1f} mOhm (est.)",
        f"conductor length: {result.conductor_length_mm:.1f} mm",
    ]
    return board, DeviceSummary(f"Inductor {name}", lines, [("single", board)])


# --- single-board transformer ----------------------------------------------
def make_transformer(*, primary_turns: float = 6, secondary_turns: float = 6,
                     primary_layers: int = 2, secondary_layers: int = 2,
                     interleave: bool = True,
                     primary_width: float = 0.4, primary_clearance: float = 0.3,
                     secondary_width: float = 0.4, secondary_clearance: float = 0.3,
                     sides: int = 64, copper_oz: float = 1.0, name: str = "T1",
                     core: Core | None = None, shape: Shape | None = None,
                     outer_diameter: float | None = 24.0,
                     material: "str | Material | None" = None, air_gap_mm: float = 0.0,
                     peak_current_a: float | None = None, volt_seconds: float | None = None,
                     dielectric_mm: float = 0.2, temp_c: float = 100.0
                     ) -> tuple[Board, DeviceSummary]:
    """Concentric planar transformer with independent primary/secondary rules.

    With ``material`` you also get magnetizing inductance, a saturation check and
    a 1-D **leakage inductance** estimate (which reflects the P/S interleaving).
    """
    if core is not None:
        outer_diameter = None
    mat = _as_material(material)
    pri_shape, pri_inset = _resolve(core, shape, outer_diameter,
                                    primary_turns, primary_width, primary_clearance)
    sec_shape, sec_inset = _resolve(core, shape, outer_diameter,
                                    secondary_turns, secondary_width, secondary_clearance)
    total = primary_layers + secondary_layers

    board = Board(copper_layers=total, title=f"Planar Transformer {name}")
    pri_net = board.add_net(f"{name}-PRI")
    sec_net = board.add_net(f"{name}-SEC")

    if interleave:
        pri_layers, sec_layers, p, s = [], [], 0, 0
        for i in range(total):
            if (i % 2 == 0 and p < primary_layers) or s >= secondary_layers:
                pri_layers.append(i); p += 1
            else:
                sec_layers.append(i); s += 1
    else:
        pri_layers = list(range(primary_layers))
        sec_layers = list(range(primary_layers, total))

    pri = Coil(turns=primary_turns, trace_width=primary_width,
               clearance=primary_clearance, layer_indices=pri_layers,
               net=pri_net, shape=pri_shape, inset_total=pri_inset,
               name="PRI", sides=sides)
    sec = Coil(turns=secondary_turns, trace_width=secondary_width,
               clearance=secondary_clearance, layer_indices=sec_layers,
               net=sec_net, shape=sec_shape, inset_total=sec_inset,
               name="SEC", sides=sides, stagger_deg=10.0)
    pres = pri.build(board)
    sres = sec.build(board)

    for term, lbl in zip(pres.terminals, (f"{name}-P1", f"{name}-P2")):
        _lead_out(board, pri_shape, term, length=1.5, width=primary_width, label=lbl)
    for term, lbl in zip(sres.terminals, (f"{name}-S1", f"{name}-S2")):
        _lead_out(board, sec_shape, term, length=3.0, width=secondary_width, label=lbl)
    _finish_outline(board, core, pri_shape)

    n_pri = primary_turns * primary_layers
    n_sec = secondary_turns * secondary_layers
    Lp = _inductance_of(pres, n_pri, sides)
    Ls = _inductance_of(sres, n_sec, sides)
    lines = []
    if core is not None:
        lines += core.summary_lines()
    lines += [
        f"primary         : {n_pri:g} turns, layers {pri_layers}, "
        f"{primary_width}/{primary_clearance} mm w/clr",
        f"secondary       : {n_sec:g} turns, layers {sec_layers}, "
        f"{secondary_width}/{secondary_clearance} mm w/clr",
        f"turns ratio     : {n_pri:g}:{n_sec:g} ({n_pri / n_sec:.2f})",
        f"Rp / Rs         : {pres.resistance_mohm(primary_width, copper_oz):.1f} / "
        f"{sres.resistance_mohm(secondary_width, copper_oz):.1f} mOhm (est.)",
        f"coupling        : {'interleaved' if interleave else 'stacked'}",
    ]
    if mat is not None and core is not None:
        lines += _core_inductance_lines(n_pri, core, mat, air_gap_mm,
                                        peak_current_a, volt_seconds, temp_c)
    else:
        lines.append(f"Lp / Ls         : {Lp * 1e6:.2f} / {Ls * 1e6:.2f} uH (air-core est.)")

    # 1-D leakage estimate from the physical layer stack
    stack = [StackLayer("P" if i in pri_layers else "S",
                        primary_turns if i in pri_layers else secondary_turns)
             for i in range(total)]
    breadth = max(pri_inset, sec_inset)
    leak = leakage_inductance(
        stack, primary_turns=n_pri, secondary_turns=n_sec,
        mlt_mm=_mlt_mm(pri_shape, pri_inset), breadth_mm=breadth,
        copper_mm=copper_thickness_mm(copper_oz), dielectric_mm=dielectric_mm)
    lines.append(f"leakage (pri)   : {leak * 1e9:.0f} nH (est., "
                 f"{'interleaved' if interleave else 'stacked'})")
    return board, DeviceSummary(f"Transformer {name}", lines, [("single", board)])


# --- multi-board (stacked PCB) winding --------------------------------------
def _column_angles(n_boards: int, phase: float = 0.0) -> list[float]:
    """``n_boards + 1`` evenly spaced angles for the connection pin columns."""
    n = n_boards + 1
    return [phase + 2.0 * math.pi * j / n for j in range(n)]


def _column_point(shape: Shape, angle: float, pin: Pin) -> Point:
    px, py = shape.point_at(angle, 0.0)
    ux, uy = shape.outward_unit(angle, 0.0)
    return (px + ux * pin.gap, py + uy * pin.gap)


def _build_winding_over_boards(
    boards: list[Board], *, shape: Shape, turns: float, layer_indices: list[int],
    trace_width: float, clearance: float, sides: int, angles: list[float],
    pin: Pin, net_name: str, lead_prefix: str, inset_total: float | None = None,
) -> float:
    """Add one winding, split across ``boards``, joined at shared pin columns."""
    if len(layer_indices) % 2:
        raise ValueError("layers per board must be even so both ends sit on the outer rail")
    columns = [_column_point(shape, a, pin) for a in angles]
    total_len = 0.0
    n = len(boards)

    for b, board in enumerate(boards):
        net = board.add_net(f"{net_name}{b + 1}")
        coil = Coil(turns=turns, trace_width=trace_width, clearance=clearance,
                    layer_indices=layer_indices, net=net, shape=shape,
                    inset_total=inset_total, name=net_name, sides=sides,
                    terminal_angles=(angles[b], angles[b + 1]))
        res = coil.build(board)
        total_len += res.conductor_length_mm

        for term, col_idx in zip(res.terminals, (b, b + 1)):
            colpt = columns[col_idx]
            board.add_track([term.xy, colpt], trace_width, term.layer_index, net)
            board.add_via(colpt, net, size=pin.pad, drill=pin.drill)
            tag = "IN" if col_idx == b else "OUT"
            board.add_text(f"{lead_prefix}{col_idx}", (colpt[0], colpt[1] - 1.2),
                           layer_index=0, size=0.8)
        # pins that pass through but don't connect on this board -> clearance holes
        for j, colpt in enumerate(columns):
            if j not in (b, b + 1):
                board.add_circle(colpt, pin.drill / 2.0 + 0.1)
    return total_len


def make_inductor_stack(
    *, turns_per_layer: float = 6, layers_per_board: int = 2, num_boards: int = 4,
    trace_width: float = 0.4, clearance: float = 0.3, sides: int = 64,
    copper_oz: float = 1.0, name: str = "L1", pin: Pin | None = None,
    core: Core | None = None, shape: Shape | None = None,
    outer_diameter: float | None = 24.0,
) -> DeviceSummary:
    """Split one inductor winding across ``num_boards`` stacked PCBs.

    Each board carries ``layers_per_board`` copper layers; boards connect in
    series through vertical pin columns shared at identical (x, y) on every
    board, so a header pin at each column joins one board's OUT to the next
    board's IN.  Columns ``0`` and ``num_boards`` are the external terminals.
    """
    if core is not None:
        outer_diameter = None
    shape, inset = _resolve(core, shape, outer_diameter,
                            turns_per_layer, trace_width, clearance)
    pin = pin or Pin()
    angles = _column_angles(num_boards)

    boards = [Board(copper_layers=layers_per_board,
                    title=f"Planar Inductor {name} board {b + 1}/{num_boards}")
              for b in range(num_boards)]
    length = _build_winding_over_boards(
        boards, shape=shape, turns=turns_per_layer, layer_indices=list(range(layers_per_board)),
        trace_width=trace_width, clearance=clearance, sides=sides, angles=angles,
        pin=pin, net_name=name, lead_prefix="C", inset_total=inset)

    for b, board in enumerate(boards):
        _finish_outline(board, core, shape, margin=pin.gap + pin.pad)

    n_total = turns_per_layer * layers_per_board * num_boards
    # one big equivalent coil for the inductance estimate
    from .windings import CoilResult
    eq = CoilResult([], length, n_total, inset, shape)
    L = _inductance_of(eq, n_total, sides)

    lines = []
    if core is not None:
        lines += core.summary_lines()
    lines += [
        f"boards          : {num_boards} x {layers_per_board}-layer "
        f"= {num_boards * layers_per_board} layers total",
        f"turns/layer     : {turns_per_layer:g}   total turns: {n_total:g}",
        f"pin columns     : {num_boards + 1} (C0..C{num_boards}); C0 & "
        f"C{num_boards} are the terminals",
        f"inductance      : {L * 1e6:.2f} uH (est., unity coupling)",
        f"DC resistance   : {eq.resistance_mohm(trace_width, copper_oz):.1f} mOhm (est., series)",
        f"conductor length: {length:.1f} mm total",
        "assembly        : stack boards aligned, solder a header pin at each column",
    ]
    summary = DeviceSummary(f"Inductor {name} (stacked)", lines,
                            [(f"board{b + 1}of{num_boards}", bd)
                             for b, bd in enumerate(boards)])
    return summary


def make_transformer_stack(
    *, primary_turns: float = 4, secondary_turns: float = 4,
    primary_layers_per_board: int = 2, secondary_layers_per_board: int = 2,
    num_boards: int = 4,
    primary_width: float = 0.4, primary_clearance: float = 0.3,
    secondary_width: float = 0.4, secondary_clearance: float = 0.3,
    sides: int = 64, copper_oz: float = 1.0, name: str = "T1", pin: Pin | None = None,
    core: Core | None = None, shape: Shape | None = None,
    outer_diameter: float | None = 28.0,
) -> DeviceSummary:
    """Split a transformer across stacked PCBs.

    Each board carries ``primary_layers_per_board`` primary layers and
    ``secondary_layers_per_board`` secondary layers (both must be even so each
    winding's ends sit on the outer rail).  Primary slices are series-joined
    through one pin-column set, secondary slices through a second, offset set.
    """
    if primary_layers_per_board % 2 or secondary_layers_per_board % 2:
        raise ValueError("primary/secondary layers per board must each be even")
    if core is not None:
        outer_diameter = None
    pri_shape, pri_inset = _resolve(core, shape, outer_diameter,
                                    primary_turns, primary_width, primary_clearance)
    sec_shape, sec_inset = _resolve(core, shape, outer_diameter,
                                    secondary_turns, secondary_width, secondary_clearance)
    pin = pin or Pin()
    layers_per_board = primary_layers_per_board + secondary_layers_per_board
    pri_layers = list(range(primary_layers_per_board))
    sec_layers = list(range(primary_layers_per_board, layers_per_board))
    # two column sets, offset so primary & secondary pins never coincide
    span = 2.0 * math.pi / (num_boards + 1)
    pri_angles = _column_angles(num_boards, phase=0.0)
    sec_angles = _column_angles(num_boards, phase=span / 2.0)

    boards = [Board(copper_layers=layers_per_board,
                    title=f"Planar Transformer {name} board {b + 1}/{num_boards}")
              for b in range(num_boards)]

    pri_len = _build_winding_over_boards(
        boards, shape=pri_shape, turns=primary_turns, layer_indices=pri_layers,
        trace_width=primary_width, clearance=primary_clearance, sides=sides,
        angles=pri_angles, pin=pin, net_name=f"{name}P", lead_prefix="P",
        inset_total=pri_inset)
    sec_len = _build_winding_over_boards(
        boards, shape=sec_shape, turns=secondary_turns, layer_indices=sec_layers,
        trace_width=secondary_width, clearance=secondary_clearance, sides=sides,
        angles=sec_angles, pin=pin, net_name=f"{name}S", lead_prefix="S",
        inset_total=sec_inset)

    for board in boards:
        _finish_outline(board, core, pri_shape, margin=pin.gap + pin.pad)

    n_pri = primary_turns * primary_layers_per_board * num_boards
    n_sec = secondary_turns * secondary_layers_per_board * num_boards
    lines = []
    if core is not None:
        lines += core.summary_lines()
    lines += [
        f"boards          : {num_boards} x {layers_per_board}-layer",
        f"primary         : {n_pri:g} turns total (layers {pri_layers}/board), "
        f"columns P0..P{num_boards}",
        f"secondary       : {n_sec:g} turns total (layers {sec_layers}/board), "
        f"columns S0..S{num_boards}",
        f"turns ratio     : {n_pri:g}:{n_sec:g} ({n_pri / n_sec:.2f})",
        f"conductor length: P {pri_len:.0f} mm / S {sec_len:.0f} mm",
        "assembly        : stack & pin the P columns and S columns separately",
    ]
    return DeviceSummary(f"Transformer {name} (stacked)", lines,
                         [(f"board{b + 1}of{num_boards}", bd)
                          for b, bd in enumerate(boards)])
