"""Soft-ferrite material database (for magnetics physics).

Initial permeability ``mu_i`` and saturation flux density ``Bsat`` are the two
numbers that drive inductance and saturation.  Values are transcribed from
Ferroxcube and TDK/EPCOS material datasheets; ``Bsat`` is quoted at 25 C and at
100 C (the design-relevant figure).  Treat them as nominal (ferrite mu_i has a
+-20-25% spread) and confirm against the datasheet for the exact grade/lot.

Sources:
  Ferroxcube "Soft Ferrites - material survey" and per-grade datasheets
  (ferroxcube.com / ferroxcube.home.pl).
  TDK/EPCOS SIFERRIT material datasheets (tdk-electronics.tdk.com).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Material:
    name: str
    manufacturer: str
    mu_i: float                 # initial (relative) permeability
    bsat_mt_25: float           # saturation flux density at 25 C (mT)
    bsat_mt_100: float          # ... at 100 C (mT) - use this for design
    tc_c: float                 # Curie temperature (C)
    f_min_khz: float            # useful frequency range
    f_max_khz: float
    note: str = ""

    def bsat_t(self, temp_c: float = 100.0) -> float:
        """Saturation flux density (tesla) at 25 or 100 C (nearest)."""
        b = self.bsat_mt_25 if temp_c < 62.5 else self.bsat_mt_100
        return b / 1000.0


# mu_i and Bsat(25) are datasheet values; Bsat(100) are the standard ~datasheet
# figures for each grade.  f-range is the typical power-conversion window.
MATERIALS: dict[str, Material] = {
    # Ferroxcube
    "3C90": Material("3C90", "Ferroxcube", 2300, 470, 380, 220, 25, 200),
    "3C94": Material("3C94", "Ferroxcube", 2300, 470, 380, 220, 25, 300),
    "3C95": Material("3C95", "Ferroxcube", 3000, 530, 410, 215, 50, 500,
                     "all-temperature, high Bsat"),
    "3C97": Material("3C97", "Ferroxcube", 3000, 530, 410, 215, 50, 500),
    "3F3": Material("3F3", "Ferroxcube", 2000, 440, 370, 200, 200, 700),
    "3F4": Material("3F4", "Ferroxcube", 900, 410, 350, 220, 500, 2000,
                    "high frequency"),
    "3F36": Material("3F36", "Ferroxcube", 1600, 430, 360, 230, 500, 2000),
    # TDK / EPCOS (SIFERRIT)
    "N87": Material("N87", "TDK", 2200, 490, 390, 210, 100, 500),
    "N95": Material("N95", "TDK", 2000, 530, 410, 215, 100, 500,
                    "flat temperature behaviour"),
    "N97": Material("N97", "TDK", 2300, 490, 410, 230, 100, 500,
                    "low loss"),
    "N49": Material("N49", "TDK", 1500, 490, 460, 240, 300, 1000,
                    "HF, high Bsat at 100 C"),
}


def get_material(name: str) -> Material:
    key = name.strip().upper()
    if key in MATERIALS:
        return MATERIALS[key]
    raise KeyError(f"unknown material '{name}'. Known: {', '.join(MATERIALS)}")


def list_materials() -> list[str]:
    return list(MATERIALS)
