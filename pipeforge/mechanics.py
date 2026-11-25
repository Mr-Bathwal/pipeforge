"""Engineering estimates for rotary-draw bending: wall thickness change and springback.

Every function here is an **engineering estimate** from classical bending
theory, not a measurement or a finite-element result. The derivations,
assumptions and sources are in docs/ENGINEERING_NOTES.md (sections 2 and 3),
each with a worked example that tests/test_mechanics.py reproduces.

Notation: OD outside diameter, t wall, r_m = (OD - t)/2 mean radius,
R centerline radius (CLR), E Young's modulus, sigma a flow stress.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .materials import Material

LABEL = "engineering estimate"


@dataclass(frozen=True)
class WallChange:
    t_outer: float  #: wall at the extrados (outside of the bend), mm
    t_inner: float  #: wall at the intrados (inside of the bend), mm
    thinning_pct: float  #: outer wall loss, % of nominal wall
    thickening_pct: float  #: inner wall gain, % of nominal wall
    outer_strain: float  #: engineering axial strain at the extrados
    inner_strain: float  #: engineering axial strain at the intrados (negative)
    label: str = LABEL


def wall_change(od: float, wall: float, clr: float) -> WallChange:
    """Wall thickness at the outside and inside of a bend.

    Assumes the neutral axis stays on the centerline, constant volume, and
    no change in the hoop direction, so the wall strain is equal and opposite
    to the axial strain. The axial stretch of the extrados fibre at radius
    R + OD/2 is (R + OD/2) / R, which gives t_o = t R / (R + OD/2), and
    likewise t_i = t R / (R - OD/2). Real benders move the neutral axis
    inwards, and a pressure die and booster reduce thinning, so this is an
    upper estimate of thinning for an unboosted bend.
    """
    if clr <= od / 2:
        raise ValueError("CLR must exceed OD/2 for the inside of the bend to exist")
    t_o = wall * clr / (clr + od / 2.0)
    t_i = wall * clr / (clr - od / 2.0)
    return WallChange(
        t_outer=t_o,
        t_inner=t_i,
        thinning_pct=100.0 * (wall - t_o) / wall,
        thickening_pct=100.0 * (t_i - wall) / wall,
        outer_strain=(od / 2.0) / clr,
        inner_strain=-(od / 2.0) / clr,
    )


def _moment_factor(alpha: float) -> float:
    """M / Mp for a thin-walled tube whose elastic core reaches angle alpha.

    The fibre at angle phi from the neutral axis sits at y = r_m sin(phi).
    Fibres with phi < alpha are elastic; the rest carry the flow stress.
    Integrating sigma * y around the ring gives
    M = 4 r_m^2 t sigma [cos(alpha) + (alpha/2 - sin(2 alpha)/4) / sin(alpha)],
    and Mp = 4 r_m^2 t sigma is the fully plastic moment.
    """
    if alpha <= 1e-12:
        return 1.0
    if alpha >= math.pi / 2:
        raise ValueError("section is fully elastic; no permanent bend")
    return math.cos(alpha) + (alpha / 2.0 - math.sin(2.0 * alpha) / 4.0) / math.sin(alpha)


@dataclass(frozen=True)
class Springback:
    springback_deg: float  #: angle the bend opens by after unloading
    ratio: float  #: springback / bend angle
    radius_after: float  #: arc radius after unloading, mm
    plastic_fraction: float  #: fraction of the section past yield, 0..1
    flow_stress: float  #: MPa used
    label: str = LABEL


def springback(angle_deg: float, clr: float, od: float, wall: float, e_mpa: float, flow_mpa: float) -> Springback:
    """Springback of a thin-walled tube bent to *angle_deg* at radius *clr*.

    Elastic, perfectly plastic material at *flow_mpa*; the elastic unloading
    curvature is M / (E I) with I = pi r_m^3 t. The arc keeps its length while
    it unloads, so the angle falls in proportion to the curvature:
    springback = angle * R * M / (E I).
    """
    if angle_deg <= 0 or clr <= 0:
        raise ValueError("angle and CLR must be positive")
    r_m = (od - wall) / 2.0
    kappa = 1.0 / clr
    y_e = flow_mpa / (e_mpa * kappa)  # distance from the neutral axis where yield is reached
    if y_e >= r_m:
        raise ValueError("the bend is elastic at this radius: it would spring back fully")
    alpha = math.asin(y_e / r_m)
    m_over_mp = _moment_factor(alpha)
    moment = 4.0 * r_m**2 * wall * flow_mpa * m_over_mp
    inertia = math.pi * r_m**3 * wall
    d_kappa = moment / (e_mpa * inertia)
    ratio = d_kappa / kappa
    sb = angle_deg * ratio
    return Springback(
        springback_deg=sb,
        ratio=ratio,
        radius_after=clr / (1.0 - ratio),
        plastic_fraction=1.0 - 2.0 * alpha / math.pi,
        flow_stress=flow_mpa,
    )


@dataclass(frozen=True)
class SpringbackBand:
    low: Springback  #: flow stress = minimum yield (proof) strength
    mid: Springback  #: flow stress = mean of yield and tensile strength
    high: Springback  #: flow stress = minimum tensile strength
    label: str = LABEL


def springback_band(angle_deg: float, clr: float, od: float, wall: float, material: Material) -> SpringbackBand:
    """Springback with three flow stresses, because hardening is not modelled.

    Bending strains at the outer fibre are OD / (2 CLR), several percent for
    any real bend, so the material has hardened past yield. The band runs
    from the yield strength (no hardening) to the tensile strength (fully
    hardened); the mean of the two is a common single-value flow stress.
    """
    sy = material.yield_mpa
    if sy is None:
        raise ValueError(f"{material.grade} has no specified minimum yield strength")
    su = material.tensile_mpa
    e = material.e_mpa
    return SpringbackBand(
        low=springback(angle_deg, clr, od, wall, e, sy),
        mid=springback(angle_deg, clr, od, wall, e, (sy + su) / 2.0),
        high=springback(angle_deg, clr, od, wall, e, su),
    )


def physics_model(od: float, wall: float, material: Material, which: str = "mid"):  # type: ignore[no-untyped-def]
    """A springback model for compensation.compensate: (angle, CLR) -> deg."""

    def model(angle_deg: float, clr: float) -> float:
        band = springback_band(angle_deg, clr, od, wall, material)
        return getattr(band, which).springback_deg

    return model


def ovality_risk(od: float, wall: float, clr: float, mandrel: bool) -> str:
    """A flag, not a number: 'low', 'medium' or 'high' risk of ovality past 8 %.

    The thresholds follow the bend die selection chart used in dfm.py: thin
    walls (high OD/t) at tight radii (low CLR/OD) flatten unless a mandrel
    supports the bore. See ENGINEERING_NOTES 3.2 for why no closed-form
    ovality number is given.
    """
    wf = od / wall
    d = clr / od
    if mandrel:
        return "low" if wf <= 40 else "medium"
    if d >= 3.0 and wf <= 15:
        return "low"
    if d >= 2.0 and wf <= 20:
        return "medium"
    return "high"
