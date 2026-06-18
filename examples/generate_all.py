"""Generate every demo design into the ``designs/`` folder.

Produces a .kicad_pcb + .png preview for each example board, a topology
comparison, and a designs/INDEX.md summarising them.  Run from the project root:

    python examples/generate_all.py
"""

import io
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planarmag import (
    Core, Leg, Winding, WireWound, convert_report, get_core, get_material,
    make_inductor, make_inductor_stack, make_transformer, make_transformer_stack,
)
from planarmag.topology import ConverterSpec, compare

OUT = os.path.join(ROOT, "designs")
os.makedirs(OUT, exist_ok=True)
index: list[tuple[str, str]] = []


def _render(board, name):
    try:
        from planarmag.preview import render_png
        render_png(board, os.path.join(OUT, f"{name}.png"))
    except Exception as exc:                      # matplotlib optional
        print(f"   (preview skipped for {name}: {exc})")


def emit(name, board, desc):
    board.save(os.path.join(OUT, f"{name}.kicad_pcb"))
    _render(board, name)
    index.append((name, f"{board.copper_layers}-layer", desc))
    print(f"  {name:<34} {board.copper_layers} layers")


def emit_stack(name, summary, desc):
    for label, board in summary.boards:
        full = f"{name}_{label}"
        board.save(os.path.join(OUT, f"{full}.kicad_pcb"))
        _render(board, full)
    n = len(summary.boards)
    index.append((name, f"{n} boards", desc))
    print(f"  {name:<34} {n} stacked boards")


print("Generating designs/ ...")

# --- single-board inductors -------------------------------------------------
b, _ = make_inductor(turns=8, outer_diameter=20, copper_layers=2, sides=64, name="L1")
emit("inductor_2layer_circular", b, "8 turns/layer, 2 layers, circular, 20 mm")

b, _ = make_inductor(turns=6, outer_diameter=20, copper_layers=4, sides=8, name="L2")
emit("inductor_4layer_octagon", b, "6 turns/layer, 4 layers, octagonal")

b, _ = make_inductor(turns=5, copper_layers=2, core=get_core("ROUND10"), sides=80,
                     material="3F3", air_gap_mm=0.3, name="Lrod")
emit("inductor_round_core", b, "round-leg core, 3F3, 0.3 mm gap")

# --- single-board transformers ----------------------------------------------
b, _ = make_transformer(primary_turns=6, secondary_turns=3, outer_diameter=26,
                        primary_width=0.5, secondary_width=0.3, name="T1")
emit("transformer_2to1_circular", b, "2:1, 4-layer interleaved, circular")

b, _ = make_transformer(primary_turns=5, secondary_turns=5,
                        core=Core.rect_leg("myE", 6.4, 9.3, 6.0), sides=120,
                        primary_width=0.5, secondary_width=0.3, name="Tcore")
emit("transformer_rect_core_racetrack", b, "racetrack on a rectangular leg")

b, _ = make_transformer(primary_turns=8, secondary_turns=4, core=get_core("E32/6/20"),
                        sides=120, material="3C95", air_gap_mm=0.2,
                        peak_current_a=2.0, name="Te32")
emit("transformer_E32_3C95", b, "real E32 core, 3C95, full physics")

# --- multi-leg core ---------------------------------------------------------
core = Core("custom3leg", legs=[
    Leg(shape="rect", width=6, length=14, wound=True, cutout=True),
    Leg(shape="round", pos=(16.0, 0.0), diameter=5, cutout=True),
    Leg(shape="round", pos=(-16.0, 0.0), diameter=5, cutout=True),
], window_radial=6.0)
b, _ = make_inductor(turns=5, copper_layers=2, core=core, sides=120, name="L3leg")
emit("inductor_multileg_3leg", b, "centre + two outer legs at +/-16 mm")

# --- stacked (multi-PCB) ----------------------------------------------------
st = make_inductor_stack(turns_per_layer=6, layers_per_board=2, num_boards=4,
                         outer_diameter=24, name="Lstk")
emit_stack("inductor_stack_4x2layer", st, "48-turn inductor split over 4 boards")

st = make_transformer_stack(primary_turns=4, secondary_turns=4,
                            primary_layers_per_board=2, secondary_layers_per_board=2,
                            num_boards=3, outer_diameter=28, name="Tstk")
emit_stack("transformer_stack_3boards", st, "transformer split over 3 boards")

# --- the worked PLT32 400V->24V 220W LLC demo (7-layer, 4 windings) ----------
with redirect_stdout(io.StringIO()):
    import demo_plt32_llc as demo
emit("demo_plt32_400V_24V_220W_LLC", demo.board,
     "PLT32 LLC, 27:4 + primary & secondary bias")

# --- text artefacts: topology comparison + a conversion survey --------------
spec = ConverterSpec(vin=400, vout=24, power=220, freq=150e3, vin_min=380, vdiode=0.6)
with open(os.path.join(OUT, "topology_comparison.txt"), "w", encoding="utf-8") as fh:
    fh.write(compare(spec, ns_turns=4, ae_mm2=130) + "\n")

wirewound = WireWound(primary=Winding(turns=27, area_mm2=0.06),
                      secondary=Winding(turns=4, area_mm2=0.50))
with open(os.path.join(OUT, "wirewound_to_planar.txt"), "w", encoding="utf-8") as fh:
    fh.write(convert_report(wirewound, cores=["E32/6/20"], copper_oz=(2.0, 4.0)) + "\n")

# --- index ------------------------------------------------------------------
with open(os.path.join(OUT, "INDEX.md"), "w", encoding="utf-8") as fh:
    fh.write("# Generated designs\n\n")
    fh.write("Each entry has a `.kicad_pcb` (opens in KiCad 8/9/10) and a `.png` preview.\n\n")
    fh.write("| design | size | description |\n|---|---|---|\n")
    for name, size, desc in index:
        fh.write(f"| `{name}` | {size} | {desc} |\n")
    fh.write("\nText reports: `topology_comparison.txt`, `wirewound_to_planar.txt`.\n")

print(f"\nDone -> {OUT}")
print(f"  {len(index)} designs, "
      f"{len([f for f in os.listdir(OUT) if f.endswith('.kicad_pcb')])} board files")
