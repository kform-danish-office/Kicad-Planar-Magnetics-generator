"""Physics: magnetizing & leakage inductance, saturation, and layer sizing."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planarmag import (
    gap_for_inductance,
    get_core,
    get_material,
    magnetizing_inductance,
    make_transformer,
    plan_for_inductance,
    turns_for_inductance,
)

core = get_core("E32/6/20")
mat = get_material("3F3")

# Magnetizing inductance vs air gap.
for gap in (0.0, 0.1, 0.5, 1.0):
    L = magnetizing_inductance(12, core, mat, gap)
    print(f"12T on {core.name}/{mat.name}, gap {gap:.1f} mm -> {L * 1e6:7.1f} uH")
print()

# Solve the gap for a target inductance.
gap = gap_for_inductance(33e-6, turns=12, core=core, material=mat)
print(f"gap for 33 uH at 12 turns: {gap:.3f} mm")
print(f"turns for 33 uH ungapped : {turns_for_inductance(33e-6, core, mat):.1f}")
print()

# How many 4-layer boards to hit 250 uH?
plan = plan_for_inductance(250e-6, core=core, material=mat, air_gap_mm=0.2,
                           layers_per_board=4, turns_per_layer=6)
print(plan.note)
print(" ", plan.line())
print()

# A transformer with full physics: magnetizing, saturation and leakage.
board, summary = make_transformer(primary_turns=8, secondary_turns=4, core=core,
                                  sides=120, material="3F3", air_gap_mm=0.2,
                                  peak_current_a=2.0, name="Tphys")
board.save("out/transformer_physics.kicad_pcb")
print(summary)
