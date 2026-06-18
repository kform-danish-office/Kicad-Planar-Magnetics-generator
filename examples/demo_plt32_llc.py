"""DEMO: 400 V -> 24 V, 220 W planar transformer on a PLT32 (E32/PLT32) core.

A 27:4 main ratio with a primary-side and a secondary-side bias winding, sized
for an LLC half-bridge (the natural topology for 400 V in / 24 V out at this
ratio).  Builds a real 7-layer .kicad_pcb and prints the full design report.

Assumptions (stated, not hidden): LLC half-bridge so the transformer primary
sees Vin/2 = 200 V; 96% efficiency; 150 kHz; 4 oz copper.
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planarmag import (
    Coil, get_core, get_material, magnetizing_inductance, gap_for_inductance,
)
from planarmag.kicad import Board
from planarmag.devices import _resolve, _lead_out, _finish_outline, _mlt_mm
from planarmag.physics import (
    StackLayer, copper_thickness_mm, leakage_inductance, saturation_check,
)
from planarmag.topology import ConverterSpec, compare, get_topology, operating_point

# ---- spec ------------------------------------------------------------------
TOPOLOGY = "LLC half-bridge"            # <-- select the topology here
Np, Ns = 27, 4
copper_oz = 4.0
spec = ConverterSpec(vin=400, vout=24, power=220, freq=150e3,
                     vin_min=380, vin_max=420, vdiode=0.6, efficiency=0.96)

# PLT32 = E32/6/20 core + PLT32 plate -> E/PLT effective le = 35.1 mm
core = copy.copy(get_core("E32/6/20")); core.le = 35.1; core.Ve = 4560
mat = get_material("3C95")

print(compare(spec, ns_turns=Ns, ae_mm2=core.Ae))      # topology comparison
print()

# operating point for the chosen topology
op = operating_point(spec, TOPOLOGY, np_turns=Np, ns_turns=Ns, ae_mm2=core.Ae)
Vpri, Iout = op.v_primary, spec.iout
Ipri, Isec = op.primary_rms_a, op.secondary_rms_a
f, Iin = spec.freq, spec.pin / spec.vin
vpt = spec.vout / Ns                                   # volts per turn (sec ref)
n_pbias = round(12.0 / vpt)
n_sbias = round(12.0 / vpt)

# ---- magnetics / gap / saturation -----------------------------------------
Lm_target = 400e-6                     # LLC tank value (set per your resonant design)
gap = gap_for_inductance(Lm_target, Np, core, mat)
Lm = magnetizing_inductance(Np, core, mat, gap)
sat = saturation_check(op.b_peak_t, mat, 100.0)

# ---- build the board: 8 layers, P/S interleaved + biases + shield ----------
# KiCad needs an even copper count, so the 8th layer carries a Faraday shield
# (a single open turn tied to primary ground) - useful for CM noise at 400 V.
# layer:  0   1   2   3   4     5     6      7
# wind :  P   S   P   S   Pbias Sbias SHIELD (spare)
board = Board(copper_layers=8, title="PLT32 400V-24V 220W LLC")
windings = [
    ("PRI", 9, [0, 2, 4], 0.50, 0.25, 1.5),    # 9T x3 = 27T
    ("SEC", 2, [1, 3], 2.40, 0.30, 3.0),       # 2T x2 = 4T, wide for 9 A
    ("PBIAS", n_pbias, [5], 0.50, 0.30, 4.5),
    ("SBIAS", n_sbias, [6], 1.00, 0.30, 6.0),
    ("SHIELD", 0.85, [7], 1.50, 0.30, 7.5),    # open turn, electrostatic screen
]
results = {}
for name, t, layers, w, clr, lead in windings:
    net = board.add_net(name)
    shape, inset = _resolve(core, None, None, t, w, clr)
    coil = Coil(turns=t, trace_width=w, clearance=clr, layer_indices=layers,
                net=net, shape=shape, inset_total=inset, name=name, sides=120)
    res = coil.build(board)
    results[name] = (res, w, shape)
    for term, lbl in zip(res.terminals, (f"{name}1", f"{name}2")):
        _lead_out(board, shape, term, length=lead, width=w, label=lbl)
_finish_outline(board, core, results["PRI"][2])
board.save("out/demo_plt32.kicad_pcb")

# ---- leakage (1-D MMF over the P/S stack; bias windings ~ spacers) ----------
# physical order L0..L7 (bias + shield carry ~0 load current -> MMF spacers)
stack = [StackLayer("P", 9), StackLayer("S", 2), StackLayer("P", 9),
         StackLayer("S", 2), StackLayer("P", 9), StackLayer("S", 0),
         StackLayer("S", 0), StackLayer("S", 0)]
pri_res, pri_w, pri_shape = results["PRI"]
sec_res, sec_w, _ = results["SEC"]
leak = leakage_inductance(stack, primary_turns=Np, secondary_turns=Ns,
                          mlt_mm=_mlt_mm(pri_shape, pri_res.inset_total),
                          breadth_mm=sec_res.inset_total,
                          copper_mm=copper_thickness_mm(copper_oz), dielectric_mm=0.2)

Rp = pri_res.resistance_mohm(pri_w, copper_oz)
Rs = sec_res.resistance_mohm(sec_w, copper_oz)

# ---- report ----------------------------------------------------------------
print(f"""PLT32 PLANAR TRANSFORMER  -  400 V -> 24 V, {spec.power:.0f} W ({TOPOLOGY})
================================================================
core            : E32/PLT32 (E/PLT), {mat.name}, Ae {core.Ae:.0f} mm2, le {core.le} mm
ratio           : {Np}:{Ns}  ({Np/Ns:.2f})   volts/turn {vpt:.1f}
operating       : {f/1e3:.0f} kHz, primary swing {Vpri:.0f} V, 4 oz copper
currents        : Iin {Iin:.2f} A (avg), Ipri ~{Ipri:.1f} A, Iout {Iout:.1f} A
windings        : PRI 27T (3 layers) | SEC 4T (2 layers, {sec_w:.1f} mm wide)
                  PBIAS {n_pbias}T (~{n_pbias*vpt:.0f} V) | SBIAS {n_sbias}T (~{n_sbias*vpt:.0f} V) | Faraday shield
air gap         : {gap:.3f} mm  ->  Lm {Lm*1e6:.0f} uH (LLC magnetizing)
saturation      : {sat.line()}
leakage (pri)   : {leak*1e9:.0f} nH (est., P/S interleaved)
winding DCR     : Rp {Rp:.0f} mOhm | Rs {Rs:.1f} mOhm  -> Psec_cu ~{Iout**2*Rs/1e3:.1f} W
board           : 8 copper layers (incl. shield), out/demo_plt32.kicad_pcb
""")

try:
    from planarmag.preview import render_png
    render_png(board, "out/preview_plt32.png")
except Exception as exc:        # matplotlib optional
    print(f"(preview skipped: {exc})")
