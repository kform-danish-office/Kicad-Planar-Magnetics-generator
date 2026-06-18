"""Split one inductor winding across several stacked PCBs.

Useful when a winding needs more layers than you want on a single (expensive)
board: build it from several cheap 2- or 4-layer boards stacked and pinned.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planarmag import make_inductor_stack, make_transformer_stack, Pin

# A 48-turn inductor as four 2-layer boards (6 turns/layer x 2 x 4), joined by
# header pins at five shared columns.  Writes one .kicad_pcb per board.
stack = make_inductor_stack(
    turns_per_layer=6, layers_per_board=2, num_boards=4,
    outer_diameter=24.0, trace_width=0.4, clearance=0.3,
    pin=Pin(drill=0.7, pad=1.4, gap=2.0), name="Lstk",
)
print(stack)
print("wrote:", stack.save_all("out"))
print()

# A transformer split across three boards: 2 primary + 2 secondary layers each.
xfmr = make_transformer_stack(
    primary_turns=4, secondary_turns=4,
    primary_layers_per_board=2, secondary_layers_per_board=2,
    num_boards=3, outer_diameter=28.0, name="Tstk",
)
print(xfmr)
print("wrote:", xfmr.save_all("out"))
