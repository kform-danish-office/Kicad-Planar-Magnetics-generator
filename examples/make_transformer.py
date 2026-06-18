"""Generate example planar transformers, incl. a core-fitted one."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planarmag import Core, make_transformer

# A 4-layer 2:1 interleaved transformer on a plain circular outline.
board, summary = make_transformer(
    primary_turns=6, secondary_turns=3, outer_diameter=26.0,
    primary_layers=2, secondary_layers=2, interleave=True,
    primary_width=0.5, primary_clearance=0.3,    # heavier primary copper
    secondary_width=0.3, secondary_clearance=0.3,
    name="T1",
)
board.save("out/transformer_2to1.kicad_pcb")
print(summary)
print()

# The same idea fitted to a rectangular-leg core: the winding becomes a
# racetrack hugging the centre leg, and the leg cut-out is added automatically.
core = Core.rect_leg("myE", width=6.4, length=9.3, window_radial=6.0)
board, summary = make_transformer(
    primary_turns=5, secondary_turns=5, core=core, sides=120,
    primary_width=0.5, secondary_width=0.3, name="Tcore",
)
board.save("out/transformer_rectcore.kicad_pcb")
print(summary)
