"""Command-line interface for generating planar magnetic boards.

Examples::

    # single 4-layer inductor, 22 mm
    python -m planarmag inductor --turns 10 --od 22 --layers 4 -o out/L.kicad_pcb

    # inductor split across four stacked 2-layer boards -> writes to a folder
    python -m planarmag inductor --turns 6 --layers 2 --boards 4 -o out/Lstack

    # transformer fitted to a rectangular-leg core, per-winding trace widths
    python -m planarmag transformer --pri 6 --sec 3 --leg-rect 6.4 9.3 --window 6 \
        --pri-width 0.5 --sec-width 0.3 -o out/T.kicad_pcb

    # transformer on a named (nominal) library core
    python -m planarmag transformer --pri 5 --sec 5 --core ELP32 -o out/T.kicad_pcb
"""

from __future__ import annotations

import argparse
import sys

from .convert import Winding, WireWound, convert_report
from .core import CORES, Core, get_core
from .devices import (
    make_inductor,
    make_inductor_stack,
    make_transformer,
    make_transformer_stack,
)


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--od", type=float, default=20.0, help="outer diameter (mm), if no core")
    p.add_argument("--sides", type=int, default=64,
                   help="polygon sides/turn (4=square, 8=octagon, >=40 circular)")
    p.add_argument("--copper-oz", type=float, default=1.0, help="copper weight (oz)")
    p.add_argument("--boards", type=int, default=1, help="split across N stacked PCBs")
    p.add_argument("-o", "--out", required=True,
                   help="output .kicad_pcb (single) or output folder (when --boards>1)")
    # core entry
    g = p.add_argument_group("core (optional)")
    g.add_argument("--core", help="named library core, e.g. ELP32 (nominal dims!)")
    g.add_argument("--leg-round", type=float, metavar="DIA",
                   help="round centre-leg diameter (mm)")
    g.add_argument("--leg-rect", type=float, nargs=2, metavar=("W", "L"),
                   help="rectangular centre-leg width and length (mm)")
    g.add_argument("--window", type=float, help="radial winding window width (mm)")
    g.add_argument("--core-clearance", type=float, default=0.5,
                   help="copper-to-centre-leg gap (mm)")
    g.add_argument("--footprint", type=float, nargs=2, metavar=("W", "L"),
                   help="overall core footprint for the board outline (mm)")


def _add_material(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("physics (optional, needs a core)")
    g.add_argument("--material", help="ferrite grade, e.g. 3F3, 3C95, N87")
    g.add_argument("--air-gap", type=float, default=0.0, help="total air gap (mm)")
    g.add_argument("--peak-current", type=float, help="peak current (A) for saturation")
    g.add_argument("--temp", type=float, default=100.0, help="operating temp (C)")


def _core_from_args(args) -> Core | None:
    if args.core:
        return get_core(args.core)
    if args.leg_round is not None or args.leg_rect is not None:
        if args.window is None:
            raise SystemExit("--window is required when entering a custom core leg")
        fp = tuple(args.footprint) if args.footprint else None
        if args.leg_round is not None:
            return Core.round_leg("custom", args.leg_round, args.window,
                                  footprint=fp, core_clearance=args.core_clearance)
        w, l = args.leg_rect
        return Core.rect_leg("custom", w, l, args.window,
                             footprint=fp, core_clearance=args.core_clearance)
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="planarmag", description="Generate planar magnetic PCBs for KiCad.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ind = sub.add_parser("inductor", help="spiral inductor")
    ind.add_argument("--turns", type=float, default=8, help="turns per layer")
    ind.add_argument("--layers", type=int, default=2, help="copper layers per board")
    ind.add_argument("--width", type=float, default=0.4, help="trace width (mm)")
    ind.add_argument("--clearance", type=float, default=0.3, help="turn-to-turn gap (mm)")
    ind.add_argument("--name", default="L1")
    _add_material(ind)
    _add_common(ind)

    xf = sub.add_parser("transformer", help="planar transformer")
    xf.add_argument("--pri", type=float, default=6, help="primary turns/layer")
    xf.add_argument("--sec", type=float, default=6, help="secondary turns/layer")
    xf.add_argument("--pri-layers", type=int, default=2,
                    help="primary layers (per board; even)")
    xf.add_argument("--sec-layers", type=int, default=2,
                    help="secondary layers (per board; even)")
    xf.add_argument("--width", type=float, default=0.4, help="default trace width (mm)")
    xf.add_argument("--clearance", type=float, default=0.3, help="default gap (mm)")
    xf.add_argument("--pri-width", type=float, help="primary trace width (mm)")
    xf.add_argument("--pri-clearance", type=float, help="primary gap (mm)")
    xf.add_argument("--sec-width", type=float, help="secondary trace width (mm)")
    xf.add_argument("--sec-clearance", type=float, help="secondary gap (mm)")
    xf.add_argument("--no-interleave", action="store_true")
    xf.add_argument("--name", default="T1")
    _add_material(xf)
    xf.add_argument("--volt-seconds", type=float, help="applied V*s (for saturation)")
    _add_common(xf)

    cv = sub.add_parser("convert", help="wire-wound -> planar conversion survey")
    cv.add_argument("--pri-turns", type=int, required=True)
    cv.add_argument("--sec-turns", type=int, help="omit for an inductor")
    cv.add_argument("--pri-awg", type=int, help="primary wire AWG")
    cv.add_argument("--sec-awg", type=int, help="secondary wire AWG")
    cv.add_argument("--pri-area", type=float, help="primary copper area mm^2 (instead of AWG)")
    cv.add_argument("--sec-area", type=float, help="secondary copper area mm^2")
    cv.add_argument("--strands", type=int, default=1, help="parallel strands in wire")
    cv.add_argument("--oz", type=float, nargs="+", default=[1.0, 2.0],
                    help="copper weights to try (oz)")
    cv.add_argument("--clearance", type=float, default=0.2)
    cv.add_argument("--layers-per-board", type=int, default=4)

    sub.add_parser("cores", help="list the core library")
    sub.add_parser("materials", help="list the ferrite material library")

    tp = sub.add_parser("topology", help="compare/size converter topologies")
    tp.add_argument("--vin", type=float, required=True, help="nominal input (V)")
    tp.add_argument("--vout", type=float, required=True, help="output (V)")
    tp.add_argument("--power", type=float, required=True, help="output power (W)")
    tp.add_argument("--freq", type=float, default=150.0, help="switching freq (kHz)")
    tp.add_argument("--vin-min", type=float)
    tp.add_argument("--vin-max", type=float)
    tp.add_argument("--vdiode", type=float, default=0.5, help="rectifier drop (V)")
    tp.add_argument("--topology", help="one topology (else compare all)")
    tp.add_argument("--ns", type=int, default=4, help="secondary turns for the table")
    tp.add_argument("--core", help="library core (to show peak flux density)")

    sz = sub.add_parser("size", help="turns/layers/boards for a target inductance")
    sz.add_argument("--target-uh", type=float, required=True, help="target inductance (uH)")
    sz.add_argument("--core", required=True, help="library core, e.g. E32/6/20")
    sz.add_argument("--material", required=True, help="ferrite grade, e.g. 3F3")
    sz.add_argument("--air-gap", type=float, default=0.0, help="air gap (mm)")
    sz.add_argument("--layers-per-board", type=int, default=4)
    sz.add_argument("--turns-per-layer", type=int, help="cap turns/layer (else max that fit)")
    sz.add_argument("--width", type=float, default=0.4)
    sz.add_argument("--clearance", type=float, default=0.3)

    return parser


def _od(args) -> float | None:
    return None if (args.core or args.leg_round is not None or args.leg_rect) else args.od


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "cores":
        for name, c in CORES.items():
            tag = "" if c.verified else "  (nominal)"
            print(f"  {name:<12} window {c.window_radial} mm, Ae {c.Ae} mm2{tag}")
        return 0

    if args.cmd == "materials":
        from .materials import MATERIALS
        for m in MATERIALS.values():
            print(f"  {m.name:<6} {m.manufacturer:<10} mu_i {m.mu_i:>4g}  "
                  f"Bsat {m.bsat_mt_25:.0f}/{m.bsat_mt_100:.0f} mT (25/100C)  "
                  f"{m.f_min_khz:g}-{m.f_max_khz:g} kHz")
        return 0

    if args.cmd == "topology":
        from .topology import ConverterSpec, compare, operating_point
        spec = ConverterSpec(vin=args.vin, vout=args.vout, power=args.power,
                             freq=args.freq * 1e3, vin_min=args.vin_min,
                             vin_max=args.vin_max, vdiode=args.vdiode)
        ae = get_core(args.core).Ae if args.core else None
        if args.topology:
            op = operating_point(spec, args.topology, ns_turns=args.ns,
                                 np_turns=None, ae_mm2=ae)
            print(op.report())
        else:
            print(compare(spec, ns_turns=args.ns, ae_mm2=ae))
        return 0

    if args.cmd == "size":
        from .sizing import plan_for_inductance
        plan = plan_for_inductance(
            args.target_uh * 1e-6, core=get_core(args.core), material=args.material,
            layers_per_board=args.layers_per_board, turns_per_layer=args.turns_per_layer,
            air_gap_mm=args.air_gap, trace_width=args.width, clearance=args.clearance)
        print(plan.note)
        print(" ", plan.line())
        return 0

    if args.cmd == "convert":
        pri = Winding(turns=args.pri_turns, awg=args.pri_awg,
                      strands=args.strands, area_mm2=args.pri_area)
        sec = None
        if args.sec_turns:
            sec = Winding(turns=args.sec_turns, awg=args.sec_awg,
                          strands=args.strands, area_mm2=args.sec_area)
        spec = WireWound(primary=pri, secondary=sec)
        print(convert_report(spec, copper_oz=tuple(args.oz), clearance=args.clearance,
                             layers_per_board=args.layers_per_board))
        return 0

    core = _core_from_args(args)

    if args.cmd == "inductor":
        if args.boards > 1:
            summary = make_inductor_stack(
                turns_per_layer=args.turns, layers_per_board=args.layers,
                num_boards=args.boards, trace_width=args.width, clearance=args.clearance,
                sides=args.sides, copper_oz=args.copper_oz, name=args.name,
                core=core, outer_diameter=_od(args))
            paths = summary.save_all(args.out)
        else:
            board, summary = make_inductor(
                turns=args.turns, copper_layers=args.layers, trace_width=args.width,
                clearance=args.clearance, sides=args.sides, copper_oz=args.copper_oz,
                name=args.name, core=core, outer_diameter=_od(args),
                material=args.material, air_gap_mm=args.air_gap,
                peak_current_a=args.peak_current, temp_c=args.temp)
            board.save(args.out)
            paths = [args.out]
    else:
        pw = args.pri_width or args.width
        pc = args.pri_clearance or args.clearance
        sw = args.sec_width or args.width
        sc = args.sec_clearance or args.clearance
        if args.boards > 1:
            summary = make_transformer_stack(
                primary_turns=args.pri, secondary_turns=args.sec,
                primary_layers_per_board=args.pri_layers,
                secondary_layers_per_board=args.sec_layers, num_boards=args.boards,
                primary_width=pw, primary_clearance=pc,
                secondary_width=sw, secondary_clearance=sc, sides=args.sides,
                copper_oz=args.copper_oz, name=args.name, core=core, outer_diameter=_od(args))
            paths = summary.save_all(args.out)
        else:
            board, summary = make_transformer(
                primary_turns=args.pri, secondary_turns=args.sec,
                primary_layers=args.pri_layers, secondary_layers=args.sec_layers,
                interleave=not args.no_interleave, primary_width=pw, primary_clearance=pc,
                secondary_width=sw, secondary_clearance=sc, sides=args.sides,
                copper_oz=args.copper_oz, name=args.name, core=core, outer_diameter=_od(args),
                material=args.material, air_gap_mm=args.air_gap,
                peak_current_a=args.peak_current, volt_seconds=args.volt_seconds,
                temp_c=args.temp)
            board.save(args.out)
            paths = [args.out]

    print(summary)
    print("\nWrote:")
    for p in paths:
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
