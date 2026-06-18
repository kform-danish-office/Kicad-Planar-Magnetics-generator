"""Magnetic core data library (mechanical + magnetic parameters).

Each record describes a real planar core well enough to lay out a winding:
overall footprint, the radial winding window, the winding-window height (the
slot the PCB stack sits in), the effective magnetic parameters (Ae, le, Ve),
and the centre / outer leg geometry (position + cross-section).

Provenance
----------
The ``E.. / ELP..`` planar-E entries are transcribed from the individual
Ferroxcube datasheets ("Planar E cores and accessories", 2008-09-01):
  https://ferroxcube.home.pl/prod/assets/eXXYYZZ.pdf
The same dimensions apply to TDK/EPCOS ELP and other IEC-62317 planar-E cores.
The centre leg is a long rectangular bar of width ``E`` (along the core length
A) and length ~= the core depth C, confirmed by Ae = E x C. The two outer legs
run the full depth C at the A-extremes.

Round-leg entries marked ``verified=False`` are generic illustrative examples.

Lengths are millimetres; Ae mm^2; le mm; Ve mm^3.
"""

from __future__ import annotations


def _planar_e(name, A, C, D, B, leg_w, Ae, le, Ve, Wclear):
    """Build a planar-E record from datasheet dimensions."""
    leg_len = round(Ae / leg_w, 2)          # centre-leg depth (Ae = leg_w x leg_len)
    outer_w = round((A - Wclear) / 2.0, 3)  # each outer-leg width along A
    outer_x = round((Wclear + outer_w) / 2.0, 3)
    return {
        "name": name,
        "series": "planar-E",
        "manufacturer": "Ferroxcube/TDK (IEC 62317)",
        "verified": True,
        "source": "Ferroxcube datasheet 2008-09-01",
        "footprint": [A, C],
        "window_radial": round((Wclear - leg_w) / 2.0, 3),
        "window_height": D,
        "core_height_half": B,
        "Ae": Ae, "le": le, "Ve": Ve,
        "center_leg": {"shape": "rect", "width": leg_w, "length": leg_len, "pos": [0.0, 0.0]},
        "outer_legs": [
            {"shape": "rect", "width": outer_w, "length": C, "pos": [outer_x, 0.0]},
            {"shape": "rect", "width": outer_w, "length": C, "pos": [-outer_x, 0.0]},
        ],
    }


# name,            A,     C,     D,    B,     legW,  Ae,   le,   Ve,    Wclear
CORE_DATA: list[dict] = [
    _planar_e("E18/4/10", 18.0, 10.0, 2.0, 4.0, 4.0, 39.3, 24.3, 960, 14.0),
    _planar_e("E22/6/16", 21.8, 15.8, 3.2, 6.0, 5.7, 78.3, 32.5, 2550, 16.8),
    _planar_e("E32/6/20", 31.75, 20.32, 3.18, 6.35, 6.35, 130.0, 41.4, 5380, 24.9),
    _planar_e("E38/8/25", 38.1, 25.4, 4.45, 8.26, 7.6, 194.0, 52.4, 10200, 30.23),
    _planar_e("E43/10/28", 43.2, 27.9, 5.4, 9.5, 8.1, 229.0, 61.1, 13900, 34.7),
    _planar_e("E58/11/38", 58.4, 38.1, 6.5, 10.5, 8.1, 308.0, 80.6, 24600, 50.0),
    # generic round-leg example (illustrative, not a specific part)
    {
        "name": "ROUND10", "series": "round", "manufacturer": "generic",
        "verified": False, "source": "illustrative example",
        "footprint": None, "window_radial": 6.0, "window_height": 3.0,
        "Ae": 78.5, "le": None, "Ve": None,
        "center_leg": {"shape": "round", "diameter": 10.0, "pos": [0.0, 0.0]},
        "outer_legs": [],
    },
]

# friendly aliases: ELP<n> -> E<n>/.. (TDK naming)
ALIASES = {
    "ELP18": "E18/4/10", "ELP22": "E22/6/16", "ELP32": "E32/6/20",
    "ELP38": "E38/8/25", "ELP43": "E43/10/28", "ELP58": "E58/11/38",
}
