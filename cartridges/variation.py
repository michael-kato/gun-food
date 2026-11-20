"""Seeded per-copy variation: each cartridge copy is a different, in-tolerance part.

Every copy is a *realization* of its spec, drawn from a seed:

* **Dimensions** are sampled inside SAAMI's tolerance bands (``[max - tol, max]``).
  Real production doesn't fill the band evenly, so values cluster in a narrower
  process spread inside it (see PROCESS below). Body diameters share one "die" offset,
  since one die forms the whole case.
* **Loaded length** follows the factory nominal with a small spread (forum measurements:
  bulk 9mm varies a few tenths of a mm, match .223 under 0.1 mm), clamped to SAAMI's
  min/max. Roll-crimped rifle rounds seat on the bullet's cannelure instead.
* **Condition** (``CONDITIONS``): ``new`` is factory-new ammo that was tumbled, boxed and
  shipped in bulk: a few shallow dents, slight out-of-round, the odd dinged case mouth,
  small bullet runout, a light film of dust. ``fired`` is brass picked up at the range:
  body and neck expanded to the chamber, crimp gone, firing-pin crater in the primer (a
  rim crush on rimfire), an extractor nick, dented mouths, bigger dents from rocks and
  boots, tarnish and scratches, soot inside and blow-by outside, and dust.
* **Maker** (``makers.toml``, see ``sample_lot``): headstamp, case and primer finish,
  sealant, primer crimp, annealing stain, age, bullet jacket and tip paint. Drawn from
  its own random stream, so makers can be added without reshuffling the dimensions.

Pure Python, deterministic for a given seed.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field, replace

from . import specs
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
    dirt: tuple[float, float]  # material: soil / dust coverage, 0-1
    soot_in: tuple[float, float] = (0.0, 0.0)  # material: powder residue inside, 0-1
    soot_out: tuple[float, float] = (0.0, 0.0)  # material: blow-by on the neck outside, 0-1
    fired: bool = False
    body_growth: tuple[float, float] = (0.0, 0.0)  # mm on diameter, case expanded to the chamber
    neck_growth: tuple[float, float] = (0.0, 0.0)  # mm on diameter, neck released the bullet
    shoulder_forward: tuple[float, float] = (0.0, 0.0)  # mm, bottleneck cases fire-form forward
    length_growth: tuple[float, float] = (0.0, 0.0)  # mm
    primer_strike_radius: tuple[float, float] = (0.0, 0.0)  # mm, firing-pin crater
    primer_strike_depth: tuple[float, float] = (0.0, 0.0)  # mm
    rim_strike_depth: tuple[float, float] = (0.0, 0.0)  # mm, rimfire firing pin crush
    extractor_nick_chance: float = 0.0
    mouth_ding_radius: tuple[float, float] = (0.6, 1.6)  # mm
    age: tuple[float, float] = (0.0, 0.0)  # material: tarnish at least this (the maker sets the rest)
    wear: tuple[float, float] = (0.0, 0.35)  # material: scuffs and scratches along the case


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
        dirt=(0.06, 0.18),
    ),
    "fired": Condition(
        name="fired",
        dents_per_10mm=1.4,
        dent_radius=(0.8, 3.0),
        dent_depth=(0.02, 0.20),
        mouth_ding_chance=0.75,  # ejected into the brass deflector, then trodden on
        mouth_ding_depth=(0.08, 0.55),
        mouth_ding_radius=(1.0, 2.6),
        ovality=(0.0, 0.08),
        runout_sd=0.0,
        tip_ding_chance=0.0,
        edge_softening=(1.0, 1.15),
        dirt=(0.15, 0.6),  # range pickups: dust and the odd smear of soil, not caked mud
        age=(0.65, 1.0),
        wear=(0.45, 1.0),
        soot_in=(0.6, 1.0),
        soot_out=(0.4, 1.0),
        fired=True,
        body_growth=(0.03, 0.10),
        neck_growth=(0.05, 0.15),
        shoulder_forward=(0.0, 0.08),
        length_growth=(0.0, 0.05),
        primer_strike_radius=(0.55, 0.90),
        primer_strike_depth=(0.20, 0.50),
        rim_strike_depth=(0.20, 0.40),
        extractor_nick_chance=0.7,
    ),
}


@dataclass(frozen=True)
class Lot:
    """What a copy's maker decided: headstamp, finishes, sealant, tip paint."""

    maker: str
    marks: tuple[tuple[str, str, float], ...]  # ("text" | "symbol", value, clock position)
    dots: tuple[float, ...]  # clock positions of extra dots
    year: int
    case_metal: str
    primer_metal: str
    sealant: str  # "none" or a [sealants] name
    sealant_rgb: tuple[float, float, float]
    smear: float  # 0-1, how far the sealant runs over the primer face
    primer_crimp: str
    anneal: float  # 0-1, neck and shoulder annealing stain
    age: float  # 0-1, tarnish
    jacket: str
    tip: str  # "none" or a [paints] name
    tip_rgb: tuple[float, float, float]
    style: specs.Style

    @property
    def headstamp_text(self) -> str:
        return " ".join(v if k == "text" else f"<{v}>" for k, v, _ in sorted(self.marks, key=lambda m: m[2] % 12))


def _choose(rng, table: dict[str, float]) -> str:
    items = [(k, w) for k, w in table.items() if w > 0]
    x = rng.random() * sum(w for _, w in items)
    for k, w in items:
        x -= w
        if x <= 0:
            return k
    return items[-1][0]


def sample_lot(cart: Cartridge, rng: random.Random, kind: str, makers: specs.Makers, maker: str | None = None) -> Lot:
    """Pick a maker for ``cart`` (weighted, or the one named) and draw its choices."""
    table = makers.for_cartridge(cart)
    if maker is None:
        if not table:
            raise specs.SpecError(f"{cart.key}: no maker in makers.toml loads this cartridge")
        maker = _choose(rng, table)
    m = makers.makers[maker]
    year = rng.randint(*m.years)
    hs = cart.headstamp
    subs = dict(caliber=hs.caliber, military=hs.military or hs.caliber, yy=f"{year % 100:02d}", code=rng.choice(m.codes) if m.codes else "")
    marks = []
    for mk in m.marks:
        if mk.symbol:
            marks.append(("symbol", mk.symbol, mk.at))
        elif text := mk.text.format(**subs).strip():
            marks.append(("text", text, mk.at))
    taken = [at for _, _, at in marks]
    free = [h for h in range(1, 13) if all(min(abs(h - t), 12 - abs(h - t)) >= 1.5 for t in taken)]
    rng.shuffle(free)
    dots = tuple(free[: rng.randint(*m.dots)])
    case_metal = _choose(rng, m.case)
    sealant = _choose(rng, m.sealant)
    tip = _choose(rng, m.tip) if kind == "loaded" else "none"
    return Lot(
        maker=maker,
        marks=tuple(marks),
        dots=dots,
        year=year,
        case_metal=case_metal,
        primer_metal=_choose(rng, m.primer) if m.primer else cart.case.primer_cup,
        sealant=sealant,
        sealant_rgb=makers.sealants.get(sealant, (0.0, 0.0, 0.0)),
        smear=rng.uniform(*m.smear) if sealant != "none" else 0.0,
        primer_crimp=m.primer_crimp,
        anneal=rng.uniform(*m.anneal) if cart.case.bottleneck and case_metal == "brass" else 0.0,
        age=rng.uniform(*m.age),
        jacket=_choose(rng, m.jacket) if m.jacket else cart.bullet.jacket,
        tip=tip,
        tip_rgb=makers.paints.get(tip, (0.0, 0.0, 0.0)),
        style=m.style,
    )


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
    kind: str  # loaded | case | fired | bullet
    condition: str
    case: CaseSpec
    bullet: BulletSpec
    seat_depth: float
    oal: float
    crimp: Crimp | None
    case_dents: list[Dent] = field(default_factory=list)
    rim_dents: list[Dent] = field(default_factory=list)  # extractor nick, rimfire strike
    bullet_dents: list[Dent] = field(default_factory=list)
    ovality: tuple[float, float] = (0.0, 0.0)  # amplitude, phase
    runout: tuple[float, float] = (0.0, 0.0)  # tilt degrees, azimuth radians
    primer_strike: tuple[float, float] | None = None  # crater radius, depth (mm)
    dirt: float = 0.0
    soot_in: float = 0.0
    soot_out: float = 0.0
    headstamp_seed: int = 0
    lot: Lot | None = None
    age: float = 0.0  # tarnish, 0-1
    wear: float = 0.0  # scratches, 0-1
    tip_length: float = 0.0  # mm of painted tip

    def labels(self) -> dict:
        """Flat values worth storing on the object (training labels, debugging)."""
        out = {
            "seed": self.seed,
            "kind": self.kind,
            "condition": self.condition,
            "maker": self.lot.maker if self.lot else "",
            "headstamp": self.lot.headstamp_text if self.lot else "",
            "case_metal": self.case.material,
            "age": round(self.age, 3),
            "wear": round(self.wear, 3),
            "case_length": round(self.case.length, 4),
            "case_rim_dia": round(self.case.rim_dia, 4),
            "case_base_dia": round(self.case.base_dia, 4),
            "case_mouth_dia": round(self.case.mouth_dia - (self.crimp.amount if self.crimp else 0.0), 4),
            "dent_count": len(self.case_dents),
            "dirt": round(self.dirt, 3),
        }
        if not self.case.rimfire and self.lot:
            out.update(primer_metal=self.lot.primer_metal, sealant=self.lot.sealant)
        if self.kind in ("loaded", "bullet"):
            out.update(bullet_dia=round(self.bullet.dia, 4), bullet_length=round(self.bullet.length, 4), jacket=self.bullet.jacket)
            if self.lot and self.lot.tip != "none":
                out.update(tip=self.lot.tip)
        if self.kind == "loaded":
            out.update(oal=round(self.oal, 4), seat_depth=round(self.seat_depth, 4), runout_deg=round(self.runout[0], 4))
        if self.kind == "fired":
            out.update(soot_in=round(self.soot_in, 3), soot_out=round(self.soot_out, 3))
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
        head_chamfer=k.head_chamfer * soft,
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
    if cond.fired:  # brass springs most of the way out to the chamber
        grow = rng.uniform(*cond.body_growth)
        new["base_dia"] += grow
        new["length"] += rng.uniform(*cond.length_growth)
        if k.bottleneck:
            new["shoulder_dia"] += grow
            fwd = rng.uniform(*cond.shoulder_forward)
            new["shoulder_start"] += fwd
            new["neck_start"] += fwd
            new["mouth_dia"] += rng.uniform(*cond.neck_growth)
        else:
            new["mouth_dia"] = min(new["base_dia"], new["mouth_dia"] + grow + rng.uniform(0.0, 0.04))
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


def realize(
    cart: Cartridge,
    seed: int,
    kind: str = "loaded",
    condition: str | None = None,
    maker: str | None = None,
    makers: specs.Makers | None = None,
) -> Copy:
    """Sample one copy of ``cart``. ``kind``: loaded, case, fired or bullet.

    ``condition`` defaults to ``fired`` for fired cases and ``new`` otherwise. ``maker``
    picks a maker from ``makers`` (default: ``makers.toml``); otherwise one is drawn,
    weighted for this cartridge.
    """
    condition = condition or ("fired" if kind == "fired" else "new")
    cond = CONDITIONS[condition]
    rng = random.Random(seed)
    # the maker gets its own stream, so adding makers never reshuffles the dimensions
    lot_rng = random.Random(copy_seed(seed, "lot"))
    lot = sample_lot(cart, lot_rng, kind, makers or specs.default_makers(), maker)
    case = replace(sample_case(cart, rng, cond), material=lot.case_metal, primer_cup=lot.primer_metal)
    bullet = replace(sample_bullet(cart.bullet, rng), jacket=lot.jacket)

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
    if kind in ("case", "fired") and rng.random() < cond.mouth_ding_chance:
        case_dents.append(Dent(case.length - rng.uniform(0.0, 0.5), rng.uniform(0, 2 * math.pi), rng.uniform(*cond.mouth_ding_radius), rng.uniform(*cond.mouth_ding_depth)))

    rim_dents, strike = [], None
    if cond.fired:
        if case.rimfire:  # the firing pin crushes the rim edge
            rim_dents.append(Dent(case.rim_thickness * 0.5, rng.uniform(0, 2 * math.pi), rng.uniform(0.7, 1.0), rng.uniform(*cond.rim_strike_depth)))
        else:
            strike = (rng.uniform(*cond.primer_strike_radius) * case.primer_cup_dia / 4.45, rng.uniform(*cond.primer_strike_depth))
        if rng.random() < cond.extractor_nick_chance and not case.rimfire:
            rim_dents.append(Dent(case.rim_thickness * 0.6, rng.uniform(0, 2 * math.pi), rng.uniform(0.35, 0.6), rng.uniform(0.04, 0.12)))

    bullet_dents = []
    if rng.random() < cond.tip_ding_chance:
        r = bullet.dia / 2
        bullet_dents.append(Dent(bullet.length - rng.uniform(0.3, 1.2), rng.uniform(0, 2 * math.pi), rng.uniform(0.4, min(1.2, r)), rng.uniform(0.01, 0.05)))
    if kind == "bullet":  # loose bullets knock into each other on the bearing surface too
        bullet_dents += _dents(rng, _poisson(rng, 0.8), (0.5, bullet.length - bullet.nose_length), (0.4, 1.2), (0.005, 0.03))

    return Copy(
        seed=seed,
        kind=kind,
        condition=condition,
        case=case,
        bullet=bullet,
        seat_depth=seat,
        oal=oal,
        crimp=crimp,
        case_dents=case_dents,
        rim_dents=rim_dents,
        bullet_dents=bullet_dents,
        ovality=(rng.uniform(*cond.ovality), rng.uniform(0, math.pi)),
        runout=(abs(rng.gauss(0, cond.runout_sd)) if kind == "loaded" else 0.0, rng.uniform(0, 2 * math.pi)),
        primer_strike=strike,
        dirt=rng.uniform(*cond.dirt),
        soot_in=rng.uniform(*cond.soot_in),
        soot_out=rng.uniform(*cond.soot_out) if case.bottleneck or rng.random() < 0.5 else 0.0,
        headstamp_seed=rng.randrange(1 << 30),
        lot=lot,
        age=max(lot.age, lot_rng.uniform(*cond.age)),
        wear=lot_rng.uniform(*cond.wear),
        tip_length=lot_rng.uniform(0.28, 0.38) * bullet.nose_length if lot.tip != "none" else 0.0,
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
    """Radial offset (mm) at a case surface point: dents, out-of-round, rim damage."""
    c = cp.case
    if cp.rim_dents and z <= c.rim_thickness + 0.05 and r > c.rim_dia / 2 - 0.6:
        return _dent_offset(cp.rim_dents, r, z, theta)
    lo = (c.groove_top or c.rim_thickness) + 0.3
    if z < lo or r < 0.55 * c.base_dia / 2:
        return 0.0  # leave the head, pocket and web alone
    amp, phase = cp.ovality
    w = min(1.0, (z - lo) / max(c.length - lo, 1e-6))
    return amp * w * w * math.cos(2 * (theta - phase)) + _dent_offset(cp.case_dents, r, z, theta)


def bullet_offset(cp: Copy, r: float, z: float, theta: float) -> float:
    if not cp.bullet_dents or r < 0.05:
        return 0.0
    return _dent_offset(cp.bullet_dents, r, z, theta)
