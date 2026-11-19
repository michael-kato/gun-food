"""Seeded per-copy variation: each cartridge copy is a different, in-tolerance part.

Every copy is a *realization* of its spec, drawn from a seed:

* **Dimensions** are sampled inside SAAMI's tolerance bands (``[max - tol, max]``).
  Real production doesn't fill the band evenly, so values cluster in a narrower
  process spread inside it (see PROCESS below). Body diameters share one "die" offset,
  since one die forms the whole case.
* **Loaded length** follows the factory nominal with a small spread (forum measurements:
  bulk 9mm varies a few tenths of a mm, match .223 under 0.1 mm), clamped to SAAMI's
  min/max. Roll-crimped rifle rounds seat on the bullet's cannelure instead.
* **Handling damage** for factory-new ammo that was tumbled, boxed and shipped in bulk:
  a few shallow dents, slight out-of-round, the odd dinged case mouth, small bullet
  runout. ``CONDITIONS`` holds the presets; fired cases can be added there later.

Pure Python, deterministic for a given seed.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field, replace

from .profiles import Crimp
from .specs import BulletSpec, Cartridge, CaseSpec

# Where real parts sit inside a tolerance band, as a fraction of the band below max:
# mean and standard deviation. Inferred from reloading-forum lot measurements (new brass
# runs 0.1-0.25 mm under max length with about +-0.1 mm spread); not a standard.
PROCESS = {
    "length": (0.25, 0.10),
    "diameter": (0.35, 0.12),
    "rim": (0.30, 0.12),
    "headspace": (0.40, 0.12),
    "bullet_dia": (0.30, 0.12),
}


@dataclass(frozen=True)
class Condition:
    name: str
    dents_per_10mm: float  # mean dent count per 10 mm of case length
    dent_radius: tuple[float, float]  # mm
    dent_depth: tuple[float, float]  # mm
    mouth_ding_chance: float  # empty cases only; a loaded mouth is protected by the bullet
    mouth_ding_depth: tuple[float, float]
    ovality: tuple[float, float]  # radial amplitude, mm, strongest at the mouth
    runout_sd: float  # bullet tilt, degrees
    tip_ding_chance: float
    edge_softening: tuple[float, float]  # multiplier on edge fillet radii


CONDITIONS = {
    "new": Condition(
        name="new",
        dents_per_10mm=0.6,
        dent_radius=(0.8, 2.2),
        dent_depth=(0.008, 0.05),
        mouth_ding_chance=0.25,
        mouth_ding_depth=(0.02, 0.08),
        ovality=(0.0, 0.015),
        runout_sd=0.12,
        tip_ding_chance=0.3,
        edge_softening=(1.0, 1.12),
    ),
}


@dataclass(frozen=True)
class Dent:
    z: float  # mm from the head (case) or base (bullet)
    theta: float  # radians
    radius: float  # mm, on the surface
    depth: float  # mm, inward


@dataclass
class Copy:
    """One concrete cartridge, case or bullet, with every sampled value."""

    seed: int
    kind: str  # loaded | case | bullet
    case: CaseSpec
    bullet: BulletSpec
    seat_depth: float
    oal: float
    crimp: Crimp | None
    case_dents: list[Dent] = field(default_factory=list)
    bullet_dents: list[Dent] = field(default_factory=list)
    ovality: tuple[float, float] = (0.0, 0.0)  # amplitude, phase
    runout: tuple[float, float] = (0.0, 0.0)  # tilt degrees, azimuth radians
    headstamp_seed: int = 0

    def labels(self) -> dict:
        """Flat values worth storing on the object (training labels, debugging)."""
        out = {
            "seed": self.seed,
            "kind": self.kind,
            "case_length": round(self.case.length, 4),
            "case_rim_dia": round(self.case.rim_dia, 4),
            "case_base_dia": round(self.case.base_dia, 4),
            "case_mouth_dia": round(self.case.mouth_dia - (self.crimp.amount if self.crimp else 0.0), 4),
            "bullet_dia": round(self.bullet.dia, 4),
            "bullet_length": round(self.bullet.length, 4),
            "dent_count": len(self.case_dents),
        }
        if self.kind == "loaded":
            out.update(oal=round(self.oal, 4), seat_depth=round(self.seat_depth, 4), runout_deg=round(self.runout[0], 4))
        return out


def copy_seed(seed: int, *parts) -> int:
    """Stable seed for one copy (Python's hash() is randomized per process)."""
    h = hashlib.blake2b(":".join(map(str, (seed, *parts))).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") & 0x7FFFFFFF


def _band(rng, vmax, tol, kind, shared=None):
    if tol <= 0:
        return vmax
    mean, sd = PROCESS[kind]
    f = shared + rng.gauss(0, 0.04) if shared is not None else rng.gauss(mean, sd)
    return vmax - tol * min(1.0, max(0.0, f))


def _poisson(rng, lam):
    k, p, limit = 0, 1.0, math.exp(-lam)
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def sample_case(cart: Cartridge, rng: random.Random, cond: Condition) -> CaseSpec:
    k = cart.case
    die = min(1.0, max(0.0, rng.gauss(*PROCESS["diameter"])))
    body = cart.tol("body_dia_tol")
    soft = rng.uniform(*cond.edge_softening)
    new = dict(
        length=_band(rng, k.length, cart.tol("length_tol"), "length"),
        base_dia=_band(rng, k.base_dia, body, "diameter", die),
        mouth_dia=_band(rng, k.mouth_dia, body, "diameter", die),
        rim_dia=_band(rng, k.rim_dia, cart.tol("rim_dia_tol"), "rim"),
        rim_thickness=_band(rng, k.rim_thickness, cart.tol("rim_thickness_tol"), "rim"),
        shoulder_radius=k.shoulder_radius * soft,
        neck_radius=k.neck_radius * soft,
        rim_chamfer=min(0.40, k.rim_chamfer * soft),
    )
    if k.bottleneck:
        new["shoulder_dia"] = _band(rng, k.shoulder_dia, body, "diameter", die)
        shift = _band(rng, 0.0, cart.tol("headspace_tol"), "headspace")
        new["shoulder_start"] = k.shoulder_start + shift
        new["neck_start"] = k.neck_start + shift
    if k.rimless:
        new["groove_dia"] = _band(rng, k.groove_dia, cart.tol("groove_dia_tol"), "rim")
    if k.base_dia < k.mouth_dia + 0.02:  # straight walls: never let the mouth end up wider than the base
        new["mouth_dia"] = min(new["mouth_dia"], new["base_dia"])
    return replace(k, **new)


def sample_bullet(b: BulletSpec, rng: random.Random) -> BulletSpec:
    length = rng.gauss(b.length, b.length_sd)
    nose = min(length * 0.75, rng.gauss(b.nose_length, b.length_sd))
    tip = max(0.3, rng.gauss(b.tip_dia, 0.05 if b.tip == "round" else 0.08))
    new = dict(
        dia=_band(rng, b.dia, b.dia_tol, "bullet_dia"),
        length=length,
        nose_length=nose,
        tip_dia=min(tip, b.dia * 0.9),
    )
    if b.cannelure_z is not None:
        new["cannelure_z"] = rng.gauss(b.cannelure_z, 0.06)
    if b.boattail_length:
        new["boattail_length"] = max(0.3, rng.gauss(b.boattail_length, 0.04))
    if b.heel_dia:
        new["heel_length"] = rng.gauss(b.heel_length, 0.04)
    return replace(b, **new)


def _dents(rng, count, z_range, radius, depth):
    lo, hi = z_range
    out = []
    for _ in range(count):
        u = rng.random()
        out.append(Dent(rng.uniform(lo, hi), rng.uniform(0, 2 * math.pi), rng.uniform(*radius), depth[0] + (depth[1] - depth[0]) * u * u))
    return out


def realize(cart: Cartridge, seed: int, kind: str = "loaded", condition: str = "new") -> Copy:
    """Sample one in-tolerance copy of ``cart``. ``kind``: loaded, case or bullet."""
    cond = CONDITIONS[condition]
    rng = random.Random(seed)
    case = sample_case(cart, rng, cond)
    bullet = sample_bullet(cart.bullet, rng)

    if bullet.heel_dia:
        seat = bullet.heel_length
    elif cart.seats_on_cannelure:
        seat = bullet.cannelure_z + 0.35 + rng.gauss(0, 0.04)
    else:
        oal = rng.gauss(cart.oal, cart.oal_sd)
        seat = bullet.length - (oal - case.length)
    oal = case.length + bullet.length - seat
    if not cart.oal_min <= oal <= cart.oal_max:  # keep inside SAAMI's loaded-length limits
        oal = min(cart.oal_max, max(cart.oal_min, oal))
        seat = bullet.length - (oal - case.length)

    crimp = None
    if kind == "loaded" and cart.crimp != "none":
        crimp = Crimp(cart.crimp, max(0.0, rng.gauss(cart.crimp_amount, cart.crimp_amount * 0.25)), cart.crimp_length)

    body_lo = (case.groove_top or case.rim_thickness) + 0.8
    n = _poisson(rng, cond.dents_per_10mm * case.length / 10)
    case_dents = _dents(rng, n, (body_lo, case.length - 0.4), cond.dent_radius, cond.dent_depth)
    if kind == "case" and rng.random() < cond.mouth_ding_chance:
        case_dents.append(Dent(case.length - rng.uniform(0.0, 0.5), rng.uniform(0, 2 * math.pi), rng.uniform(0.6, 1.3), rng.uniform(*cond.mouth_ding_depth)))

    bullet_dents = []
    if rng.random() < cond.tip_ding_chance:
        r = bullet.dia / 2
        bullet_dents.append(Dent(bullet.length - rng.uniform(0.3, 1.2), rng.uniform(0, 2 * math.pi), rng.uniform(0.4, min(1.2, r)), rng.uniform(0.01, 0.05)))
    if kind == "bullet":  # loose bullets knock into each other on the bearing surface too
        bullet_dents += _dents(rng, _poisson(rng, 0.8), (0.5, bullet.length - bullet.nose_length), (0.4, 1.2), (0.005, 0.03))

    return Copy(
        seed=seed,
        kind=kind,
        case=case,
        bullet=bullet,
        seat_depth=seat,
        oal=oal,
        crimp=crimp,
        case_dents=case_dents,
        bullet_dents=bullet_dents,
        ovality=(rng.uniform(*cond.ovality), rng.uniform(0, math.pi)),
        runout=(abs(rng.gauss(0, cond.runout_sd)) if kind == "loaded" else 0.0, rng.uniform(0, 2 * math.pi)),
        headstamp_seed=rng.randrange(1 << 30),
    )


# ---------------------------------------------------------------- surface displacement


def _dent_offset(dents, r, z, theta):
    off = 0.0
    for d in dents:
        dth = (theta - d.theta + math.pi) % (2 * math.pi) - math.pi
        dist = math.hypot(dth * max(r, 0.5), z - d.z)
        if dist < d.radius:
            off -= d.depth * 0.5 * (1 + math.cos(math.pi * dist / d.radius))
    return off


def case_offset(cp: Copy, r: float, z: float, theta: float) -> float:
    """Radial offset (mm) at a case surface point: dents and out-of-round on the body."""
    c = cp.case
    lo = (c.groove_top or c.rim_thickness) + 0.3
    if z < lo or r < 0.55 * c.base_dia / 2:
        return 0.0  # leave the head, rim, pocket and web alone
    amp, phase = cp.ovality
    w = min(1.0, (z - lo) / max(c.length - lo, 1e-6))
    return amp * w * w * math.cos(2 * (theta - phase)) + _dent_offset(cp.case_dents, r, z, theta)


def bullet_offset(cp: Copy, r: float, z: float, theta: float) -> float:
    if not cp.bullet_dents or r < 0.05:
        return 0.0
    return _dent_offset(cp.bullet_dents, r, z, theta)
