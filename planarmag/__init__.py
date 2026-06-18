"""planarmag - a KiCad planar-magnetics PCB generator.

Generate spiral inductors and planar transformers as ``.kicad_pcb`` boards,
ready to open in KiCad 8/9/10.  No KiCad runtime or ``pcbnew`` needed to build
boards - the s-expression file is written directly.

Quick start::

    from planarmag import make_inductor
    board, summary = make_inductor(turns=8, outer_diameter=20, copper_layers=2)
    board.save("inductor.kicad_pcb")
    print(summary)

Fit to a core, or split across stacked boards::

    from planarmag import make_transformer, make_inductor_stack, Core
    core = Core.rect_leg("myE", width=6.4, length=9.3, window_radial=6.0)
    board, s = make_transformer(primary_turns=5, secondary_turns=5, core=core)

    stack = make_inductor_stack(turns_per_layer=6, layers_per_board=2, num_boards=4)
    stack.save_all("out")
"""

from .convert import (
    AWG_AREA_MM2,
    PlanarDesign,
    Winding,
    WireWound,
    awg_area,
    convert,
    convert_report,
)
from .core import CORES, Core, Leg, get_core, list_cores
from .materials import MATERIALS, Material, get_material, list_materials
from .physics import (
    effective_permeability,
    gap_for_inductance,
    leakage_inductance,
    magnetizing_inductance,
    saturation_check,
    turns_for_inductance,
)
from .sizing import LayerPlan, layers_for_turns, plan_for_inductance
from .topology import (
    TOPOLOGIES,
    ConverterSpec,
    OperatingPoint,
    compare as compare_topologies,
    get_topology,
    list_topologies,
    operating_point,
)
from .devices import (
    DeviceSummary,
    Pin,
    make_inductor,
    make_inductor_stack,
    make_transformer,
    make_transformer_stack,
    spiral_inductance_h,
)
from .geometry import polygon_spiral, shape_spiral
from .kicad import Board
from .shapes import Circle, RoundedRect, Shape
from .windings import Coil, CoilResult, Terminal

__version__ = "1.4.0"

__all__ = [
    "Board",
    "Coil",
    "CoilResult",
    "Terminal",
    "Shape",
    "Circle",
    "RoundedRect",
    "Core",
    "Leg",
    "CORES",
    "get_core",
    "list_cores",
    "WireWound",
    "Winding",
    "PlanarDesign",
    "convert",
    "convert_report",
    "awg_area",
    "AWG_AREA_MM2",
    "Material",
    "MATERIALS",
    "get_material",
    "list_materials",
    "magnetizing_inductance",
    "turns_for_inductance",
    "gap_for_inductance",
    "effective_permeability",
    "leakage_inductance",
    "saturation_check",
    "LayerPlan",
    "layers_for_turns",
    "plan_for_inductance",
    "ConverterSpec",
    "OperatingPoint",
    "TOPOLOGIES",
    "get_topology",
    "list_topologies",
    "operating_point",
    "compare_topologies",
    "DeviceSummary",
    "Pin",
    "make_inductor",
    "make_inductor_stack",
    "make_transformer",
    "make_transformer_stack",
    "spiral_inductance_h",
    "polygon_spiral",
    "shape_spiral",
]
