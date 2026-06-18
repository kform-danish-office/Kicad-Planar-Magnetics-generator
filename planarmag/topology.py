"""Converter topology selection and transformer operating-point equations.

Pick a topology and a converter spec (Vin/Vout/power/frequency) and this gives
the transformer turns ratio, duty, the primary voltage that drives the core
flux, the peak flux density, approximate winding RMS currents, and what the
magnetizing inductance / air gap must do.  First-order design equations - good
for selection and sizing, confirm the final design against the controller's
datasheet equations.

Supported: flyback, forward, two-switch forward, active-clamp forward,
half-bridge, full-bridge, push-pull, LLC half-bridge, LLC full-bridge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ConverterSpec:
    vin: float                       # nominal input (V)
    vout: float                      # output (V)
    power: float                     # output power (W)
    freq: float                      # switching frequency (Hz)
    vin_min: float | None = None
    vin_max: float | None = None
    vdiode: float = 0.5              # secondary rectifier drop (V)
    efficiency: float = 0.95

    def __post_init__(self) -> None:
        if self.vin_min is None:
            self.vin_min = self.vin
        if self.vin_max is None:
            self.vin_max = self.vin

    @property
    def iout(self) -> float:
        return self.power / self.vout

    @property
    def pin(self) -> float:
        return self.power / self.efficiency

    @property
    def vsec(self) -> float:
        return self.vout + self.vdiode


@dataclass
class OperatingPoint:
    topology: str
    turns_ratio: float          # recommended Np/Ns
    duty_max: float
    v_primary: float            # amplitude driving the core flux (V)
    bipolar: bool               # bipolar (B/H) swing vs unipolar
    energy_storage: bool        # transformer stores energy -> needs a gap
    primary_rms_a: float
    secondary_rms_a: float
    inductance_note: str
    # filled when a core + turns are supplied:
    np: int | None = None
    ns: int | None = None
    b_peak_t: float | None = None

    def report(self) -> str:
        out = [f"{self.topology}",
               f"  turns ratio Np:Ns : {self.turns_ratio:.2f}"
               + (f"  -> {self.np}:{self.ns}" if self.np else ""),
               f"  duty (max)        : {self.duty_max:.2f}",
               f"  primary swing     : {self.v_primary:.0f} V "
               f"({'bipolar' if self.bipolar else 'unipolar'})",
               f"  I_pri / I_sec rms : {self.primary_rms_a:.2f} / "
               f"{self.secondary_rms_a:.1f} A (approx)",
               f"  magnetics         : {self.inductance_note}"]
        if self.b_peak_t is not None:
            out.append(f"  B_peak            : {self.b_peak_t * 1e3:.0f} mT")
        return "\n".join(out)


class Topology:
    name = "base"
    bipolar = True
    energy_storage = False
    duty_max = 0.45
    inductance_note = "magnetizing only"

    def turns_ratio(self, s: ConverterSpec) -> float:        # Np/Ns
        raise NotImplementedError

    def v_primary(self, s: ConverterSpec) -> float:          # flux-driving amplitude
        raise NotImplementedError

    def duty(self, s: ConverterSpec) -> float:
        return self.duty_max

    def flux_swing(self, s: ConverterSpec, np_turns: float, ae_mm2: float) -> float:
        """Full flux swing dB (tesla) over the primary on-time."""
        return self.v_primary(s) * self.duty(s) / (np_turns * ae_mm2 * 1e-6 * s.freq)

    def b_peak(self, s: ConverterSpec, np_turns: float, ae_mm2: float) -> float:
        dB = self.flux_swing(s, np_turns, ae_mm2)
        return dB / 2.0 if self.bipolar else dB

    def primary_rms(self, s: ConverterSpec, n: float) -> float:
        return (s.iout / n) * math.sqrt(self.duty_max)

    def secondary_rms(self, s: ConverterSpec) -> float:
        return s.iout

    def operating_point(self, s: ConverterSpec) -> OperatingPoint:
        n = self.turns_ratio(s)
        return OperatingPoint(
            topology=self.name, turns_ratio=n, duty_max=self.duty(s),
            v_primary=self.v_primary(s), bipolar=self.bipolar,
            energy_storage=self.energy_storage,
            primary_rms_a=self.primary_rms(s, n),
            secondary_rms_a=self.secondary_rms(s),
            inductance_note=self.inductance_note)


# --- concrete topologies ----------------------------------------------------
class Flyback(Topology):
    name = "flyback"
    bipolar = False
    energy_storage = True
    duty_max = 0.45
    inductance_note = "stores energy -> needs a gap; size Lp for ripple"

    def turns_ratio(self, s):
        d = self.duty_max
        return s.vin_min * d / (s.vsec * (1 - d))

    def v_primary(self, s):
        return s.vin_min

    def primary_rms(self, s, n):
        return (s.pin / s.vin_min) / math.sqrt(self.duty_max)

    def secondary_rms(self, s):
        return s.iout / math.sqrt(1 - self.duty_max)


class Forward(Topology):
    name = "forward"
    bipolar = False
    duty_max = 0.45
    inductance_note = "no energy storage; core must reset (D <= 0.5)"

    def turns_ratio(self, s):
        return s.vin_min * self.duty_max / s.vsec

    def v_primary(self, s):
        return s.vin_min


class TwoSwitchForward(Forward):
    name = "two-switch forward"
    inductance_note = "clamped reset to Vin; no energy storage"


class ActiveClampForward(Forward):
    name = "active-clamp forward"
    duty_max = 0.6
    inductance_note = "active-clamp reset enables D > 0.5; no energy storage"


class HalfBridge(Topology):
    name = "half-bridge"
    bipolar = True
    duty_max = 0.45

    def turns_ratio(self, s):
        return s.vin_min * self.duty_max / s.vsec   # Vout = (1/n) Vin D

    def v_primary(self, s):
        return s.vin / 2.0

    def primary_rms(self, s, n):
        return (s.iout / n) * math.sqrt(2 * self.duty_max)


class FullBridge(Topology):
    name = "full-bridge"
    bipolar = True
    duty_max = 0.9          # effective (both legs)

    def turns_ratio(self, s):
        return s.vin_min * self.duty_max / s.vsec

    def v_primary(self, s):
        return s.vin

    def duty(self, s):
        return self.duty_max / 2.0    # per-leg on-time for the flux swing

    def primary_rms(self, s, n):
        return (s.iout / n) * math.sqrt(self.duty_max)


class PushPull(Topology):
    name = "push-pull"
    bipolar = True
    duty_max = 0.9

    def turns_ratio(self, s):
        return s.vin_min * self.duty_max / s.vsec

    def v_primary(self, s):
        return s.vin           # each half-primary sees full Vin

    def duty(self, s):
        return self.duty_max / 2.0

    def primary_rms(self, s, n):
        return (s.iout / n) * math.sqrt(self.duty_max / 2.0)

    def secondary_rms(self, s):
        return s.iout / math.sqrt(2.0)    # centre-tapped, each half conducts


class LLCHalfBridge(Topology):
    name = "LLC half-bridge"
    bipolar = True
    duty_max = 0.5
    inductance_note = "gapped Lm set by resonant tank (ZVS); gain ~1 at fr"

    def turns_ratio(self, s):
        return (s.vin / 2.0) / s.vsec     # unity gain at resonance, nominal Vin

    def v_primary(self, s):
        return s.vin / 2.0

    def primary_rms(self, s, n):
        return 1.11 * (s.iout / n)        # ~sinusoidal + magnetizing margin

    def secondary_rms(self, s):
        return 1.11 * s.iout


class LLCFullBridge(LLCHalfBridge):
    name = "LLC full-bridge"

    def turns_ratio(self, s):
        return s.vin / s.vsec

    def v_primary(self, s):
        return s.vin


TOPOLOGIES: dict[str, Topology] = {
    t.name: t for t in (
        Flyback(), Forward(), TwoSwitchForward(), ActiveClampForward(),
        HalfBridge(), FullBridge(), PushPull(), LLCHalfBridge(), LLCFullBridge(),
    )
}
# convenient aliases
_ALIASES = {"llc": "LLC half-bridge", "llc-hb": "LLC half-bridge",
            "llc-fb": "LLC full-bridge", "2sw-forward": "two-switch forward",
            "active-clamp": "active-clamp forward", "fb": "full-bridge",
            "hb": "half-bridge"}


def get_topology(name: str) -> Topology:
    key = name.strip().lower()
    if key in _ALIASES:
        key = _ALIASES[key].lower()
    for t in TOPOLOGIES.values():
        if t.name.lower() == key:
            return t
    raise KeyError(f"unknown topology '{name}'. Known: {', '.join(TOPOLOGIES)} "
                   f"(aliases: {', '.join(_ALIASES)})")


def list_topologies() -> list[str]:
    return list(TOPOLOGIES)


def operating_point(spec: ConverterSpec, topology: str, *,
                    np_turns: int | None = None, ns_turns: int | None = None,
                    ae_mm2: float | None = None) -> OperatingPoint:
    """Operating point for ``topology``; fills B_peak if turns + Ae are given."""
    op = get_topology(topology).operating_point(spec)
    if np_turns and ns_turns:
        op.np, op.ns = np_turns, ns_turns
        if ae_mm2:
            op.b_peak_t = get_topology(topology).b_peak(spec, np_turns, ae_mm2)
    return op


def compare(spec: ConverterSpec, topologies: list[str] | None = None,
            *, ns_turns: int = 4, ae_mm2: float | None = None) -> str:
    """One-line-per-topology comparison for a spec (Ns fixed, Np from the ratio)."""
    names = topologies or list(TOPOLOGIES)
    rows = [f"Topology comparison  {spec.vin:.0f} V -> {spec.vout:.0f} V, "
            f"{spec.power:.0f} W, {spec.freq / 1e3:.0f} kHz  (Ns={ns_turns})",
            f"{'topology':<22} {'Np:Ns':>7} {'duty':>5} {'Vpri':>6} "
            f"{'Ipri':>6} {'Isec':>6}  notes"]
    for nm in names:
        op = get_topology(nm).operating_point(spec)
        np_t = max(1, round(op.turns_ratio * ns_turns))
        bnote = ""
        if ae_mm2:
            b = get_topology(nm).b_peak(spec, np_t, ae_mm2)
            bnote = f"B {b * 1e3:.0f} mT; "
        rows.append(f"{op.topology:<22} {np_t:>4}:{ns_turns:<2} {op.duty_max:>5.2f} "
                    f"{op.v_primary:>5.0f}V {op.primary_rms_a:>5.1f}A "
                    f"{op.secondary_rms_a:>5.1f}A  {bnote}"
                    f"{'gapped/energy' if op.energy_storage else op.inductance_note[:22]}")
    return "\n".join(rows)
