"""Work out how many layers / boards a design needs.

You pick ``layers_per_board`` (how many copper layers each PCB has) and a target
- either a turns count, or a magnetizing inductance on a given core/material -
and this returns the turns/layer, the layers, and the number of stacked boards
required.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .core import Core
from .materials import Material, get_material
from .physics import turns_for_inductance


@dataclass
class LayerPlan:
    turns_needed: int
    turns_per_layer: int
    series_layers: int
    parallel: int
    layers_per_board: int
    note: str = ""

    @property
    def total_layers(self) -> int:
        return self.series_layers * self.parallel

    @property
    def boards(self) -> int:
        return math.ceil(self.total_layers / self.layers_per_board)

    def line(self) -> str:
        return (f"{self.turns_needed} turns -> {self.turns_per_layer}/layer x "
                f"{self.series_layers} series"
                + (f" x {self.parallel} parallel" if self.parallel > 1 else "")
                + f" = {self.total_layers} layers "
                f"-> {self.boards} x {self.layers_per_board}-layer board(s)")


def layers_for_turns(turns_needed: int, *, turns_per_layer: int,
                     layers_per_board: int, parallel: int = 1) -> LayerPlan:
    """Layers/boards needed to realise ``turns_needed`` turns."""
    series = math.ceil(turns_needed / turns_per_layer)
    return LayerPlan(turns_needed, turns_per_layer, series, parallel, layers_per_board)


def max_turns_per_layer(core: Core, trace_width: float, clearance: float) -> int:
    """Largest turns/layer that fit the core's radial window."""
    return core.max_turns(trace_width, clearance)


def plan_for_inductance(target_h: float, *, core: Core, material: "str | Material",
                        layers_per_board: int, turns_per_layer: int | None = None,
                        air_gap_mm: float = 0.0, trace_width: float = 0.4,
                        clearance: float = 0.3) -> LayerPlan:
    """Layers/boards to reach ``target_h`` henries on ``core`` in ``material``.

    If ``turns_per_layer`` is omitted, the most that fit the window are used.
    """
    mat = get_material(material) if isinstance(material, str) else material
    n = math.ceil(turns_for_inductance(target_h, core, mat, air_gap_mm))
    tpl_max = core.max_turns(trace_width, clearance)
    if tpl_max < 1:
        return LayerPlan(n, 0, 0, 1, layers_per_board, "trace won't fit window")
    tpl = min(turns_per_layer or tpl_max, tpl_max)
    plan = layers_for_turns(n, turns_per_layer=tpl, layers_per_board=layers_per_board)
    plan.note = (f"target {target_h * 1e6:.1f} uH on {core.name}/{mat.name}, "
                 f"gap {air_gap_mm:g} mm")
    return plan
