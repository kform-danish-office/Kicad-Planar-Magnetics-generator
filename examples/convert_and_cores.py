"""Wire-wound -> planar conversion, the core library, and multi-leg cores."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planarmag import (
    Core,
    Leg,
    Winding,
    WireWound,
    convert_report,
    get_core,
    list_cores,
    make_inductor,
    make_transformer,
)

# 1) The core library (real Ferroxcube / IEC-62317 planar-E dimensions).
print("Library cores:", list_cores())
print(get_core("ELP32").summary_lines()[0])
print()

# 2) Convert a wire-wound 12:3 transformer (24 AWG primary, 18 AWG secondary)
#    into planar options - bigger core vs. more parallel layers.
spec = WireWound(primary=Winding(turns=12, awg=24),
                 secondary=Winding(turns=3, awg=18))
print(convert_report(spec, copper_oz=(1.0, 2.0)))
print()

# 3) Build a transformer fitted to a real library core.
board, summary = make_transformer(primary_turns=8, secondary_turns=4,
                                  core=get_core("E32/6/20"), sides=120,
                                  primary_width=0.5, secondary_width=0.4, name="Te32")
board.save("out/transformer_E32.kicad_pcb")
print(summary)
print()

# 4) A custom multi-leg core: centre leg wound, plus two round legs at +/-16 mm
#    that get their own board cut-outs.
core = Core("custom3leg", legs=[
    Leg(shape="rect", width=6, length=14, wound=True, cutout=True),
    Leg(shape="round", pos=(16.0, 0.0), diameter=5, cutout=True),
    Leg(shape="round", pos=(-16.0, 0.0), diameter=5, cutout=True),
], window_radial=6.0)
board, summary = make_inductor(turns=5, copper_layers=2, core=core, sides=120, name="L3leg")
board.save("out/inductor_3leg.kicad_pcb")
print(summary)
