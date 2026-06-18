"""Magnetics physics: magnetizing inductance, air gap, saturation, leakage.

All first-order engineering models (1-D), good for design sizing - confirm
critical designs with a field solver.

* Magnetizing inductance uses the gapped-core reluctance model
  ``1/mu_e = 1/mu_i + lg/le``  ->  ``L = N^2 * mu0 * mu_e * Ae / le``.
* Saturation uses ``B = L*I/(N*Ae)`` (current driven) or ``B = V*t/(N*Ae)``
  (volt-second driven).
* Leakage inductance uses the classic 1-D MMF-energy method over the physical
  layer stack: ``L_leak = mu0 * (MLT/breadth) * integral(n(z)^2 dz)`` where
  ``n(z)`` is the cumulative ampere-turns (normalised to the primary), which
  makes interleaving fall out automatically.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .core import Core
from .materials import Material

MU0 = 4.0e-7 * math.pi


# --- magnetizing inductance / air gap ---------------------------------------
def effective_permeability(mu_i: float, le_mm: float, gap_mm: float) -> float:
    """Effective permeability of a core with a total air gap ``gap_mm``."""
    if gap_mm <= 0:
        return mu_i
    return mu_i / (1.0 + mu_i * gap_mm / le_mm)


def al_value_nh(core: Core, material: Material, gap_mm: float = 0.0) -> float:
    """Inductance factor AL (nH/turn^2) for ``core`` in ``material`` with gap."""
    if core.Ae is None or core.le is None:
        raise ValueError(f"core '{core.name}' has no Ae/le for an AL calculation")
    mu_e = effective_permeability(material.mu_i, core.le, gap_mm)
    al_h = MU0 * mu_e * (core.Ae * 1e-6) / (core.le * 1e-3)   # henries/turn^2
    return al_h * 1e9


def magnetizing_inductance(turns: float, core: Core, material: Material,
                           gap_mm: float = 0.0) -> float:
    """Magnetizing inductance (henries) of ``turns`` on a gapped core."""
    return turns**2 * al_value_nh(core, material, gap_mm) * 1e-9


def turns_for_inductance(target_h: float, core: Core, material: Material,
                         gap_mm: float = 0.0) -> float:
    """Turns needed to reach ``target_h`` henries."""
    al = al_value_nh(core, material, gap_mm) * 1e-9
    return math.sqrt(target_h / al)


def gap_for_inductance(target_h: float, turns: float, core: Core,
                       material: Material) -> float:
    """Air gap (mm) that yields ``target_h`` for a fixed turns count."""
    al_target = target_h / turns**2                       # H/turn^2
    mu_e = al_target / (MU0 * (core.Ae * 1e-6) / (core.le * 1e-3))
    if mu_e >= material.mu_i:
        return 0.0                                        # ungapped already lower
    # invert mu_e = mu_i / (1 + mu_i*lg/le)
    return (material.mu_i / mu_e - 1.0) * core.le / material.mu_i


# --- saturation -------------------------------------------------------------
def flux_density_from_current(inductance_h: float, current_a: float,
                              turns: float, ae_mm2: float) -> float:
    """Peak flux density (tesla) for a peak current (B = L*I/(N*Ae))."""
    return inductance_h * current_a / (turns * ae_mm2 * 1e-6)


def flux_density_from_voltage(volt_s: float, turns: float, ae_mm2: float) -> float:
    """Peak flux density (tesla) from applied volt-seconds (B = V*t/(N*Ae))."""
    return volt_s / (turns * ae_mm2 * 1e-6)


@dataclass
class SaturationCheck:
    b_peak_t: float
    b_sat_t: float
    temp_c: float

    @property
    def margin(self) -> float:
        return self.b_sat_t / self.b_peak_t if self.b_peak_t else float("inf")

    @property
    def ok(self) -> bool:
        return self.b_peak_t <= self.b_sat_t

    def line(self) -> str:
        return (f"B_peak {self.b_peak_t * 1e3:.0f} mT vs Bsat "
                f"{self.b_sat_t * 1e3:.0f} mT @ {self.temp_c:.0f}C "
                f"(x{self.margin:.2f} margin, {'OK' if self.ok else 'SATURATED'})")


def saturation_check(b_peak_t: float, material: Material,
                     temp_c: float = 100.0) -> SaturationCheck:
    return SaturationCheck(b_peak_t, material.bsat_t(temp_c), temp_c)


# --- leakage inductance (1-D MMF energy) ------------------------------------
@dataclass
class StackLayer:
    winding: str        # "P" or "S"
    turns: float        # turns on this copper layer


def leakage_inductance(layers: list[StackLayer], *, primary_turns: float,
                       secondary_turns: float, mlt_mm: float, breadth_mm: float,
                       copper_mm: float, dielectric_mm: float) -> float:
    """Leakage inductance (H) referred to the primary, 1-D MMF-energy method.

    ``layers`` is the physical copper stack top->bottom.  ``breadth_mm`` is the
    winding breadth (radial copper-band width for a planar coil); ``copper_mm``
    the copper thickness; ``dielectric_mm`` the spacing between copper layers.
    """
    if secondary_turns <= 0:
        return 0.0
    ratio = primary_turns / secondary_turns
    n = 0.0                 # cumulative MMF normalised to the primary (turns)
    integral = 0.0          # integral of n(z)^2 dz, in mm
    for i, ly in enumerate(layers):
        delta = ly.turns if ly.winding.upper().startswith("P") else -ly.turns * ratio
        n_next = n + delta
        # copper layer: n ramps linearly -> Simpson of n^2
        integral += copper_mm * (n * n + n * n_next + n_next * n_next) / 3.0
        n = n_next
        if i < len(layers) - 1:           # dielectric gap at constant MMF
            integral += dielectric_mm * n * n
    return MU0 * (mlt_mm / breadth_mm) * (integral * 1e-3)


def copper_thickness_mm(copper_oz: float) -> float:
    """Copper foil thickness for a given plating weight."""
    return copper_oz * 0.0348      # 1 oz ~= 34.8 um
