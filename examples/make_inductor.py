"""Generate a couple of example spiral inductors."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planarmag import make_inductor

# A 2-layer, 8-turns-per-layer circular spiral inductor, 20 mm across.
board, summary = make_inductor(
    turns=8, outer_diameter=20.0, trace_width=0.4, clearance=0.3,
    copper_layers=2, sides=64, name="L1",
)
board.save("out/inductor_2layer.kicad_pcb")
print(summary)
print()

# A 4-layer octagonal inductor for higher inductance in the same footprint.
board, summary = make_inductor(
    turns=6, outer_diameter=20.0, trace_width=0.35, clearance=0.25,
    copper_layers=4, sides=8, name="L2",
)
board.save("out/inductor_4layer_oct.kicad_pcb")
print(summary)
