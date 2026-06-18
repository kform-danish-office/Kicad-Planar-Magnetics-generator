"""Tests for the planarmag package.

Run with:  python -m pytest   (or just: python tests/test_planarmag.py)
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planarmag import (
    Circle,
    Coil,
    Core,
    Leg,
    RoundedRect,
    Winding,
    WireWound,
    awg_area,
    convert,
    get_core,
    list_cores,
    make_inductor,
    make_inductor_stack,
    make_transformer,
    make_transformer_stack,
    polygon_spiral,
    shape_spiral,
)
from planarmag import (
    effective_permeability,
    gap_for_inductance,
    get_material,
    layers_for_turns,
    leakage_inductance,
    magnetizing_inductance,
    plan_for_inductance,
    saturation_check,
    turns_for_inductance,
)
from planarmag.geometry import polyline_length
from planarmag.kicad import Board, copper_layer_name
from planarmag.physics import StackLayer


def _field(summary, key):
    """Pull a leading float from the summary line containing ``key``."""
    for ln in summary.lines:
        if key in ln:
            after = ln.split(":", 1)[1].strip()
            return float(after.split()[0].split("/")[0])
    raise KeyError(key)


# --- geometry ---------------------------------------------------------------
def test_polygon_spiral_endpoints():
    pts = polygon_spiral(r_start=10, r_end=2, start_angle=0.0, sweep=4 * math.pi, sides=64)
    assert math.isclose(math.hypot(*pts[0]), 10, rel_tol=1e-9)
    assert math.isclose(math.hypot(*pts[-1]), 2, rel_tol=1e-9)
    radii = [math.hypot(*p) for p in pts]
    assert all(b <= a + 1e-9 for a, b in zip(radii, radii[1:]))


def test_shape_spiral_circle_matches_radius():
    c = Circle(10)
    pts = shape_spiral(c, start_angle=0, sweep=2 * math.pi, inset_start=0,
                       inset_end=4, sides=64)
    assert math.isclose(math.hypot(*pts[0]), 10, rel_tol=1e-9)
    assert math.isclose(math.hypot(*pts[-1]), 6, rel_tol=1e-9)  # 10 - inset 4


def test_rounded_rect_clears_leg():
    rr = RoundedRect(10, 6, 2)
    # a point on the boundary along +x sits at half-width 10
    px, py = rr.point_at(0.0, 0.0)
    assert math.isclose(px, 10, abs_tol=0.05)
    # inset by 3 pulls every side in by 3 mm
    px, _ = rr.point_at(0.0, 3.0)
    assert math.isclose(px, 7, abs_tol=0.05)


# --- layer numbering --------------------------------------------------------
def test_copper_layer_names():
    assert copper_layer_name(0, 4) == "F.Cu"
    assert copper_layer_name(1, 4) == "In1.Cu"
    assert copper_layer_name(2, 4) == "In2.Cu"
    assert copper_layer_name(3, 4) == "B.Cu"
    assert copper_layer_name(1, 2) == "B.Cu"


# --- coil / vias ------------------------------------------------------------
def test_coil_via_count_and_terminals():
    board = Board(copper_layers=4)
    net = board.add_net("L")
    coil = Coil(turns=5, trace_width=0.4, clearance=0.3, layer_indices=[0, 1, 2, 3],
                net=net, r_outer=10, name="L")
    result = coil.build(board)
    assert len(board.vias) == 3          # 4 layers -> 3 interlayer vias
    assert len(result.terminals) == 2
    assert result.turns_total == 20
    assert result.conductor_length_mm > 0


def test_vias_distinct_locations():
    board = Board(copper_layers=4)
    net = board.add_net("L")
    Coil(turns=4, trace_width=0.4, clearance=0.3, layer_indices=[0, 1, 2, 3],
         net=net, r_outer=12).build(board)
    locs = [(round(v.at[0], 3), round(v.at[1], 3)) for v in board.vias]
    assert len(locs) == len(set(locs))


def test_inset_validation():
    board = Board(copper_layers=2)
    net = board.add_net("L")
    coil = Coil(turns=100, trace_width=0.4, clearance=0.3, layer_indices=[0, 1],
                net=net, r_outer=5)
    try:
        coil.build(board)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for impossible geometry")


# --- single-board devices ---------------------------------------------------
def test_make_inductor_outputs_valid_board():
    board, summary = make_inductor(turns=8, outer_diameter=20, copper_layers=2)
    text = board.to_string()
    assert text.startswith("(kicad_pcb")
    assert text.rstrip().endswith(")")
    assert '(layer "F.Cu")' in text and "(segment" in text
    assert _field(summary, "inductance") > 0


def test_make_transformer_layer_split():
    board, summary = make_transformer(primary_turns=6, secondary_turns=3,
                                      primary_layers=2, secondary_layers=2)
    assert board.copper_layers == 4
    assert '(layer "In1.Cu")' in board.to_string()
    assert any("12:6" in ln for ln in summary.lines)  # ratio 12:6


def test_per_winding_widths_differ():
    board, _ = make_transformer(primary_turns=4, secondary_turns=4,
                                primary_width=0.6, secondary_width=0.25)
    widths = {round(s.width, 3) for s in board.segments}
    assert 0.6 in widths and 0.25 in widths


def test_inductance_scales_with_turns():
    _, s4 = make_inductor(turns=4, outer_diameter=20, copper_layers=2)
    _, s8 = make_inductor(turns=8, outer_diameter=20, copper_layers=2)
    assert _field(s8, "inductance") > _field(s4, "inductance")


def test_board_rejects_odd_layers():
    from planarmag.kicad import Board
    for bad in (1, 3, 7):
        try:
            Board(copper_layers=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {bad} copper layers")
    Board(copper_layers=8)   # even is fine


# --- cores ------------------------------------------------------------------
def test_core_rect_leg_cutout_and_fit():
    core = Core.rect_leg("E", width=6.4, length=9.3, window_radial=6.0)
    assert core.max_turns(0.4, 0.3) == int((6.0 - core.core_clearance - 0.4) // 0.7)
    board, summary = make_inductor(turns=5, copper_layers=2, core=core)
    # a rectangular leg produces a polygon cut-out on Edge.Cuts
    assert len(board.polys) == 1
    assert any("core" in ln for ln in summary.lines)


def test_core_round_leg_cutout():
    core = Core.round_leg("R", diameter=10, window_radial=5)
    board, _ = make_inductor(turns=4, copper_layers=2, core=core)
    assert len(board.circles) == 1  # round leg -> circular cut-out


def test_window_overflow_raises():
    core = Core.rect_leg("tiny", width=6, length=10, window_radial=2.0)
    try:
        make_inductor(turns=10, copper_layers=2, core=core)  # 10*0.7 = 7 mm > 2
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when winding exceeds window")


# --- core library (real data) -----------------------------------------------
def test_library_has_real_planar_e_cores():
    assert "E32/6/20" in list_cores()
    c = get_core("ELP32")               # alias resolves
    assert c.Ae == 130 and c.verified
    assert abs(c.window_radial - 9.275) < 0.01
    assert len(c.legs) == 3             # centre + 2 outer legs
    assert get_core("E32") is c         # short name resolves too


def test_library_core_draws_centre_cutout_and_ref():
    core = get_core("E32/6/20")
    board, _ = make_inductor(turns=4, copper_layers=2, core=core)
    edge = [p for p in board.polys if p.layer == "Edge.Cuts"]
    ref = [p for p in board.polys if p.layer == "Cmts.User"]
    assert len(edge) == 1 and len(ref) == 1   # leg cut-out + footprint reference


def test_arbitrary_leg_positions():
    core = Core("custom", legs=[
        Leg(shape="rect", width=6, length=10, wound=True, cutout=True),
        Leg(shape="round", pos=(15.0, 0.0), diameter=4, cutout=True),
        Leg(shape="round", pos=(-15.0, 0.0), diameter=4, cutout=True),
    ], window_radial=5.0)
    board, _ = make_inductor(turns=3, copper_layers=2, core=core)
    assert len(board.circles) == 2            # the two round legs
    assert len([p for p in board.polys if p.layer == "Edge.Cuts"]) == 1  # rect leg


# --- wire-wound -> planar conversion ----------------------------------------
def test_awg_area():
    assert abs(awg_area(24) - 0.205) < 0.01
    assert abs(awg_area(24, strands=3) - 3 * 0.205) < 0.03


def test_convert_ranks_and_tradeoff():
    spec = WireWound(primary=Winding(turns=12, awg=24),
                     secondary=Winding(turns=3, awg=18))
    designs = convert(spec, copper_oz=(2.0,))
    assert designs and designs[0].feasible
    # ranked by fewest total layers
    layers = [d.total_layers for d in designs if d.feasible]
    assert layers == sorted(layers)
    # bigger window (E58) should need no parallel on the primary
    big = next(d for d in designs if d.core_name == "E58/11/38")
    assert big.primary.parallel == 1


def test_convert_inductor_only():
    spec = WireWound(primary=Winding(turns=20, awg=26))
    designs = convert(spec, copper_oz=(1.0,))
    assert designs[0].secondary is None
    assert designs[0].primary.total_layers >= 1


# --- physics: materials, inductance, gap, saturation, leakage ---------------
def test_material_lookup():
    m = get_material("3F3")
    assert m.mu_i == 2000
    assert 0.3 < m.bsat_t(100) < 0.45


def test_effective_permeability_with_gap():
    le, mu_i = 41.4, 2000
    assert effective_permeability(mu_i, le, 0.0) == mu_i
    mu_e = effective_permeability(mu_i, le, 0.5)
    assert mu_e < mu_i and mu_e > 0


def test_magnetizing_inductance_scales_and_gap_reduces():
    core, mat = get_core("E32/6/20"), get_material("3F3")
    l10 = magnetizing_inductance(10, core, mat)
    l20 = magnetizing_inductance(20, core, mat)
    assert abs(l20 / l10 - 4.0) < 1e-6           # L ~ N^2
    assert magnetizing_inductance(10, core, mat, 0.5) < l10   # gap lowers L


def test_gap_for_inductance_roundtrip():
    core, mat = get_core("E32/6/20"), get_material("3F3")
    gap = gap_for_inductance(20e-6, 12, core, mat)
    assert gap > 0
    L = magnetizing_inductance(12, core, mat, gap)
    assert abs(L - 20e-6) / 20e-6 < 0.02


def test_turns_for_inductance():
    core, mat = get_core("E32/6/20"), get_material("3F3")
    n = turns_for_inductance(50e-6, core, mat, gap_mm=0.3)
    assert magnetizing_inductance(round(n), core, mat, 0.3) > 0


def test_saturation_check():
    mat = get_material("3F3")
    assert saturation_check(0.2, mat, 100).ok
    assert not saturation_check(0.5, mat, 100).ok


def test_leakage_interleaving_reduces():
    common = dict(primary_turns=8, secondary_turns=8, mlt_mm=60, breadth_mm=8,
                  copper_mm=0.07, dielectric_mm=0.2)
    stacked = [StackLayer("P", 4), StackLayer("P", 4),
               StackLayer("S", 4), StackLayer("S", 4)]
    interleaved = [StackLayer("P", 4), StackLayer("S", 4),
                   StackLayer("P", 4), StackLayer("S", 4)]
    assert leakage_inductance(interleaved, **common) < leakage_inductance(stacked, **common)


def test_make_inductor_with_material_reports_magnetizing():
    core = get_core("E32/6/20")
    _, s = make_inductor(turns=6, copper_layers=2, core=core, material="3F3",
                         air_gap_mm=0.3, peak_current_a=2.0)
    assert any("L (magnetizing)" in ln for ln in s.lines)
    assert any("saturation" in ln for ln in s.lines)


def test_make_transformer_reports_leakage():
    core = get_core("E32/6/20")
    _, s = make_transformer(primary_turns=8, secondary_turns=4, core=core,
                            material="3F3", air_gap_mm=0.2)
    assert any("leakage" in ln for ln in s.lines)


# --- sizing: layers / boards needed -----------------------------------------
def test_layers_for_turns():
    plan = layers_for_turns(20, turns_per_layer=6, layers_per_board=4)
    assert plan.series_layers == 4          # ceil(20/6)
    assert plan.boards == 1                  # 4 layers fit one 4-layer board


def test_plan_for_inductance_boards():
    plan = plan_for_inductance(200e-6, core=get_core("E32/6/20"), material="3F3",
                               air_gap_mm=0.1, layers_per_board=4, turns_per_layer=6)
    assert plan.turns_needed > 0
    assert plan.boards >= 1
    assert plan.total_layers == plan.series_layers * plan.parallel


# --- topology selection -----------------------------------------------------
def test_topology_lookup_and_aliases():
    from planarmag import get_topology, list_topologies
    assert len(list_topologies()) >= 8
    assert get_topology("llc").name == "LLC half-bridge"
    assert get_topology("fb").name == "full-bridge"


def test_flyback_stores_energy_others_dont():
    from planarmag import get_topology
    assert get_topology("flyback").operating_point(_spec()).energy_storage
    assert not get_topology("half-bridge").operating_point(_spec()).energy_storage


def test_full_bridge_ratio_double_half_bridge():
    from planarmag import get_topology
    s = _spec()
    n_hb = get_topology("half-bridge").turns_ratio(s)
    n_fb = get_topology("full-bridge").turns_ratio(s)
    assert abs(n_fb / n_hb - 2.0) < 0.05      # FB sees full Vin, HB sees Vin/2


def test_llc_ratio_is_unity_gain_point():
    from planarmag import get_topology
    s = _spec()
    n = get_topology("LLC half-bridge").turns_ratio(s)
    assert abs(n - (s.vin / 2) / s.vsec) < 1e-6


def test_flux_unipolar_higher_than_bipolar():
    from planarmag import operating_point
    s = _spec()
    b_fwd = operating_point(s, "forward", np_turns=28, ns_turns=4, ae_mm2=130).b_peak_t
    b_hb = operating_point(s, "half-bridge", np_turns=28, ns_turns=4, ae_mm2=130).b_peak_t
    assert b_fwd > b_hb                        # unipolar swing vs bipolar half-swing


def test_pushpull_secondary_rms_lower():
    from planarmag import get_topology
    s = _spec()
    assert get_topology("push-pull").secondary_rms(s) < get_topology("forward").secondary_rms(s)


def _spec():
    from planarmag import ConverterSpec
    return ConverterSpec(vin=400, vout=24, power=220, freq=150e3,
                         vin_min=380, vin_max=420, vdiode=0.6)


# --- multi-board stack ------------------------------------------------------
def test_inductor_stack_boards_and_columns():
    s = make_inductor_stack(turns_per_layer=5, layers_per_board=2, num_boards=4,
                            outer_diameter=24)
    assert len(s.boards) == 4
    for _, board in s.boards:
        # each board: 1 internal via + 2 active column vias = 3 plated vias
        assert len(board.vias) == 3
        # the other 3 of the 5 columns are clearance holes on this board
        assert len(board.circles) == 3


def test_stack_requires_even_layers():
    try:
        make_inductor_stack(turns_per_layer=3, layers_per_board=3, num_boards=2)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for odd layers_per_board")


def test_transformer_stack_two_windings():
    s = make_transformer_stack(primary_turns=3, secondary_turns=3,
                               primary_layers_per_board=2, secondary_layers_per_board=2,
                               num_boards=3, outer_diameter=28)
    assert len(s.boards) == 3
    # primary + secondary nets on each board (plus net 0)
    for _, board in s.boards:
        names = {n.name for n in board.nets}
        assert any("P" in n for n in names) and any("S" in n for n in names)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {fn.__name__}: {exc!r}")
    print(f"\n{len(fns) - failures}/{len(fns)} passed")
    sys.exit(1 if failures else 0)
