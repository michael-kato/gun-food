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
  New ammo always carries some factory tarnish (``Condition.age``), except from a
  ``pristine`` maker, which stays showroom-clean.
* **Bullet tarnish** follows the jacket (``JACKET_AGE``): brass jackets stay bright,
  drawn gilding metal ranges from bright to dull, plated copper comes dull.
* **Micro relief** (``Copy.micro``): a few microns of waviness on every case and bullet,
  stronger at the edges, so reflections never look machined-perfect; plus the odd small,
  sharp ding (``Condition.dings``).

Pure Python, deterministic for a given seed.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field, replace

from . import specs
from .profiles import Crimp, bullet_profile
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
    clean_burn: float = 0.0  # chance of a very clean-burning powder: hardly any residue
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
    micro: tuple[float, float] = (0.7, 1.0)  # mesh: scale on the micro relief (see mesh.micro_relief)
    dings: float = 0.0  # mean count of small sharp dings per case (bullets get a third as many)
    rim_nicks: float = 0.0  # mean count of small nicks in the rim's edge (feeding, extraction, tumbling)
    grime: tuple[float, float] = (0.0, 0.0)  # material: grime at least this (the maker sets the rest)
    ding_radius: tuple[float, float] = (0.55, 0.9)  # mm; the lathe's ~0.5 mm vertex spacing carries no smaller
    ding_depth: tuple[float, float] = (0.015, 0.04)  # mm
    # flat spots (see Flat), scaled by the copy's handling (wear, grime; few on a pristine lot)
    flats: float = 0.0  # mean count on the exposed bullet nose, any size
    speckles: float = 0.0  # mean count of tiny ones on top (up to speckle_size)
    tip_flat_chance: float = 0.0  # a flattened tip (feed ramp, a dropped round)
    rim_flats: float = 0.0  # mean count on the rim's edge, any size
    rim_speckles: float = 0.0  # and tiny ones
    macro_flats: float = 0.0  # mean count of broad, very shallow flattenings per part (case body, bullet)
    flat_size: tuple[float, float] = (0.3, 1.3)  # mm, footprint half-length; drawn skewed hard to the small end
    speckle_size: float = 0.55  # mm
    fine_scratches: float = 0.0  # mean count of tiny scratches pressed into a case (a bullet gets half), see Scratch


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
        dings=0.7,
        rim_nicks=0.8,
        flats=16.0,
        speckles=140.0,
        tip_flat_chance=0.15,
        rim_flats=5.0,
        rim_speckles=45.0,
        macro_flats=3.0,
        fine_scratches=90.0,
        wear=(0.1, 0.45),
        age=(0.15, 0.4),  # boxed ammo is never mirror-bright: toning, water spots, handling
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
        micro=(1.0, 1.6),
        dings=2.5,
        rim_nicks=2.0,
        rim_flats=14.0,
        rim_speckles=120.0,
        macro_flats=5.0,
        fine_scratches=220.0,
        flat_size=(0.3, 1.7),
        grime=(0.3, 0.7),
        ding_depth=(0.02, 0.06),
        soot_in=(0.4, 1.0),
        clean_burn=0.2,
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


# Bullet tarnish (0-1) by jacket metal, before the lot's own age is added. Brass jackets
# hold their shine; drawn gilding-metal jackets vary; plated copper is soft and matte from
# the plating bath and oxidizes faster than brass, so it comes dull.
JACKET_AGE = {
    "brass": (0.0, 0.12),
    "nickel": (0.0, 0.08),
    "gilding-metal": (0.05, 0.55),
    "copper": (0.35, 0.8),
    "lead": (0.3, 0.9),
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
    anneal_colour: str  # plain (brown to blue-grey stain) or rainbow (heat-tint interference colours)
    age: float  # 0-1, tarnish
    pristine: bool  # showroom-clean when new
    grime: float  # 0-1, grease film, oxidation mottling, micro-dings
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
        anneal_colour=_choose(rng, m.anneal_colour),
        age=rng.uniform(*m.age),
        pristine=m.pristine,
        grime=0.0 if m.pristine else rng.uniform(*m.grime),
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
    sharp: bool = False  # a ding: steep walls, pointed bottom (a dent is a smooth dish)


@dataclass(frozen=True)
class Flat:
    """A flat, or slightly dished, spot pressed in by something hard: a magazine lip, the feed
    ramp, the extractor, a bench, the next round in a bin. Inside a footprint (a stretched
    ellipse with a wobbly outline) the surface is pushed toward a plane (see
    ``mesh.press_flats``), which breaks up its reflection."""

    z: float  # mm from the head (case) or base (bullet); the bullet's length for a flattened tip
    theta: float  # radians
    radius: float  # mm, the footprint's long half-axis
    strength: float = 1.0  # how far toward the plane, 0-1 (1: dead flat)
    aspect: float = 1.0  # long axis over short
    orient: float = 0.0  # radians, the long axis's direction
    wobble: tuple = ()  # (harmonic, amplitude, phase) ripples on the outline
    cup: float = 0.0  # extra depth in the middle, as a share of the press: slightly concave
    tilt: float = 0.0  # radians off the surface: a glancing knock
    tilt_dir: float = 0.0  # radians, which way it tilts
    max_depth: float = 1.0  # mm, never pressed deeper (keeps a flattened tip inside SAAMI)
    fine: bool = True  # needs the fine mesh (the broad, gentle ones don't)


@dataclass(frozen=True)
class Scratch:
    """A tiny scratch pressed into the surface (boxes, magazines, other rounds, the range
    floor): a shallow groove along a short, slightly bent path (see ``mesh.scratch_lines``)."""

    z: float  # mm, the middle
    theta: float  # radians
    angle: float  # radians on the surface: 0 runs along the part's axis, pi/2 around it
    length: float  # mm
    width: float  # mm, half-width of the groove
    depth: float  # mm
    bend: float = 0.0  # mm, how far the middle sits off a straight line


# Flat spot and fine scratch counts were tuned on a 9mm Luger; other parts get them in
# proportion: case body area (mm^2), rim circumference (mm), exposed bullet area (mm^2).
REF_BODY, REF_RIM, REF_NOSE = 505.0, 31.4, 288.0
# Flat spots on a bullet scale with how thick it is where they land (a 9mm nose's typical
# radius, mm): on a slim rifle ogive a full-size one would press a long crease.
REF_NOSE_RADIUS = 4.0


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
    case_flats: list[Flat] = field(default_factory=list)  # on the rim's edge
    bullet_flats: list[Flat] = field(default_factory=list)
    case_scratches: list[Scratch] = field(default_factory=list)
    bullet_scratches: list[Scratch] = field(default_factory=list)
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
    bullet_age: float = 0.0  # bullet tarnish, 0-1
    grime: float = 0.0  # grease film, oxidation, micro-dings, 0-1
    micro: float = 1.0  # scale on the micro relief

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
            "pristine": bool(self.lot and self.lot.pristine),
            "grime": round(self.grime, 3),
            "wear": round(self.wear, 3),
            "case_length": round(self.case.length, 4),
            "case_rim_dia": round(self.case.rim_dia, 4),
            "case_base_dia": round(self.case.base_dia, 4),
            "case_mouth_dia": round(self.case.mouth_dia - (self.crimp.amount if self.crimp else 0.0), 4),
            "dent_count": len(self.case_dents),
            "flat_count": len(self.case_flats) + len(self.bullet_flats),
            "dirt": round(self.dirt, 3),
        }
        if not self.case.rimfire and self.lot:
            out.update(primer_metal=self.lot.primer_metal, sealant=self.lot.sealant)
        if self.lot and self.lot.anneal > 0:
            out.update(anneal=round(self.lot.anneal, 3), anneal_colour=self.lot.anneal_colour)
        if self.kind in ("loaded", "bullet"):
            out.update(bullet_dia=round(self.bullet.dia, 4), bullet_length=round(self.bullet.length, 4), jacket=self.bullet.jacket, bullet_age=round(self.bullet_age, 3))
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


def _soot_in(rng, cond: Condition) -> float:
    """Residue inside: one draw, so the copies' other values don't reshuffle. A clean-burning
    powder (``cond.clean_burn`` of lots) leaves hardly any."""
    u, (lo, hi) = rng.random(), cond.soot_in
    if u < cond.clean_burn:
        return 0.02 + 0.13 * u / cond.clean_burn
    return lo + (hi - lo) * (u - cond.clean_burn) / max(1e-9, 1 - cond.clean_burn)


def _dings(rng, count, z_range, cond: Condition):
    lo, hi = z_range
    if hi <= lo:
        return []
    return [Dent(rng.uniform(lo, hi), rng.uniform(0, 2 * math.pi), rng.uniform(*cond.ding_radius), rng.uniform(*cond.ding_depth), sharp=True) for _ in range(count)]


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

    # the odd small, sharp ding, from its own stream so the dimensions above never reshuffle
    drng = random.Random(copy_seed(seed, "dings"))
    case_dents += _dings(drng, _poisson(drng, cond.dings), (body_lo, case.length - 0.5), cond)
    for _ in range(_poisson(drng, cond.rim_nicks)):  # little nicks in the rim's edge
        rim_dents.append(Dent(drng.uniform(0.15, case.rim_thickness - 0.05), drng.uniform(0, 2 * math.pi), drng.uniform(0.3, 0.5), drng.uniform(0.02, 0.05), sharp=True))
    if kind in ("loaded", "bullet"):
        lo = seat if kind == "loaded" else 0.5
        bullet_dents += _dings(drng, _poisson(drng, cond.dings / 3), (lo + 0.3, bullet.length - 1.0), cond)

    cp = Copy(
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
        soot_in=_soot_in(rng, cond),
        soot_out=rng.uniform(*cond.soot_out) if case.bottleneck or rng.random() < 0.5 else 0.0,
        headstamp_seed=rng.randrange(1 << 30),
        lot=lot,
        age=lot.age if lot.pristine and not cond.fired else max(lot.age, lot_rng.uniform(*cond.age)),
        wear=lot_rng.uniform(*cond.wear) * (0.3 if lot.pristine and not cond.fired else 1.0),
        tip_length=lot_rng.uniform(0.28, 0.38) * bullet.nose_length if lot.tip != "none" else 0.0,
        bullet_age=_bullet_age(lot, bullet.jacket, lot_rng),
        micro=lot_rng.uniform(*cond.micro) * (0.5 if lot.pristine and not cond.fired else 1.0),
        grime=max(lot.grime, lot_rng.uniform(*cond.grime)),
    )
    if cond.fired and cp.soot_in < 0.2:  # clean powder: little blow-by either
        cp.soot_out *= 0.3
    # own streams, so nothing above reshuffles
    _add_flats(cp, cart, cond, random.Random(copy_seed(seed, "flats")))
    _add_scratches(cp, cond, random.Random(copy_seed(seed, "scratches")))
    return cp


def _add_flats(cp: Copy, cart: Cartridge, cond: Condition, rng) -> None:
    """Flat spots on the rim's edge and the exposed bullet nose: a great many tiny ones and the
    odd medium one (a cluster of two or three), more on a well-handled copy; and a few broad,
    very shallow flattenings on the case body and the bullet."""
    handling = 0.05 if cp.lot and cp.lot.pristine and not cond.fired else 0.4 + 0.6 * cp.wear + 0.8 * cp.grime
    lo_r, hi_r = cond.flat_size

    def flat(z, theta, radius=None, tilt=0.2, r_max=hi_r, gentle=1.0):
        t = rng.random() ** 3  # skewed hard toward the small end
        r = radius or lo_r * (r_max / lo_r) ** t
        t = (r - lo_r) / (hi_r - lo_r)
        return Flat(
            z, theta, r,
            strength=gentle * rng.uniform(0.4, 0.9) * (1 - 0.7 * t),  # the bigger, the gentler
            aspect=1 + 1.4 * rng.random() ** 2,
            orient=rng.uniform(0, math.pi),
            wobble=tuple((k, rng.uniform(0.0, 0.2), rng.uniform(0, 2 * math.pi)) for k in (2, 3, 5)),
            cup=rng.uniform(0.0, 0.4),
            tilt=rng.uniform(0, tilt) * (1 - 0.6 * t),  # small knocks glance: tiny tilted facets that catch the light
            tilt_dir=rng.uniform(0, 2 * math.pi),
        )

    def scatter(out, n, z_range, z_of, surf_r, tilt, r_max=hi_r, gentle=1.0, size=None):
        for _ in range(n):
            f = flat(z_of(), rng.uniform(0, 2 * math.pi), tilt=tilt, r_max=r_max, gentle=gentle)
            if size:
                f = replace(f, radius=f.radius * size(f.z))
            out.append(f)
            if f.radius > 0.5 * hi_r:  # a medium knock leaves a ragged cluster, not one neat oval
                for _ in range(rng.randint(1, 2)):
                    d, a = f.radius * rng.uniform(0.5, 0.9), rng.uniform(0, 2 * math.pi)
                    z = min(max(f.z + d * math.cos(a), z_range[0]), z_range[1])
                    sat = flat(z, f.theta + d * math.sin(a) / surf_r, f.radius * rng.uniform(0.35, 0.65), tilt, gentle=gentle)
                    out.append(replace(sat, strength=0.6 * sat.strength))

    def macro(out, n, z_range, radius):  # broad and barely there: they only bend the reflections
        for _ in range(n):
            f = flat(rng.uniform(*z_range), rng.uniform(0, 2 * math.pi), rng.uniform(*radius), 0.0)
            out.append(replace(f, strength=rng.uniform(0.1, 0.25), aspect=1 + 1.5 * rng.random(), cup=0.0, max_depth=rng.uniform(0.008, 0.025), fine=False))

    c = cp.case
    body_k, rim_k = _body_area(c) / REF_BODY, math.pi * c.rim_dia / REF_RIM
    body = ((c.groove_top or c.rim_thickness) + 1.0, c.length - 1.0)
    macro(cp.case_flats, _poisson(rng, cond.macro_flats * handling * body_k), body, (2.0, 4.5))
    rim = (0.25 * c.rim_thickness, 0.75 * c.rim_thickness)
    rim_r = min(hi_r, 0.6 * c.rim_thickness + 0.4)
    scatter(cp.case_flats, _poisson(rng, cond.rim_flats * handling * rim_k), rim, lambda: rng.uniform(*rim), c.rim_dia / 2, 0.25, rim_r)
    scatter(cp.case_flats, _poisson(rng, cond.rim_speckles * handling * rim_k), rim, lambda: rng.uniform(*rim), c.rim_dia / 2, 0.15, min(rim_r, cond.speckle_size), 0.5)
    if cp.kind not in ("loaded", "bullet"):
        return
    b = cp.bullet
    lo = (cp.seat_depth if cp.kind == "loaded" else 0.0) + 0.5
    hi = b.length - 1.2  # off the tip's dome (a flattened tip is its own kind, below)
    if hi > lo:  # a little more toward the nose, where it meets the magazine lips and the feed ramp
        nose = lambda: lo + (hi - lo) * rng.random() ** 0.7  # noqa: E731
        k = handling * _nose_area(cp) / REF_NOSE
        prof = bullet_profile(b)
        size = lambda z: min(1.0, max(0.35, _radius_at(prof, z) / REF_NOSE_RADIUS))  # noqa: E731
        macro(cp.bullet_flats, _poisson(rng, cond.macro_flats * k * 0.6), (lo, max(lo, hi - 1.0)), (1.8, 3.5))
        scatter(cp.bullet_flats, _poisson(rng, cond.flats * k), (lo, hi), nose, b.dia / 2, 0.35, size=size)
        scatter(cp.bullet_flats, _poisson(rng, cond.speckles * k), (lo, hi), nose, b.dia / 2, 0.15, cond.speckle_size, 0.5, size=size)
    if rng.random() < cond.tip_flat_chance * min(1.0, handling):
        cap = 0.15
        if cp.kind == "loaded":  # keep the round inside SAAMI's loaded length
            cap = min(cap, cp.oal - cart.oal_min - 0.02)
        if cap > 0.02:
            f = flat(b.length, 0.0, rng.uniform(0.45, 1.0), 0.4)
            cp.bullet_flats.append(replace(f, strength=rng.uniform(0.7, 1.0), aspect=min(f.aspect, 1.4), cup=0.5 * f.cup, max_depth=cap))


def _add_scratches(cp: Copy, cond: Condition, rng) -> None:
    """Tiny scratches on the case body and the exposed bullet, more on a well-handled copy:
    about half along the axis (chambering, sliding in a magazine), a fifth around it
    (tumbling), the rest any which way; mostly short."""
    handling = 0.05 if cp.lot and cp.lot.pristine and not cond.fired else 0.4 + 0.6 * cp.wear + 0.8 * cp.grime

    def scratch(z_range):
        u = rng.random()
        if u < 0.5:
            angle = rng.gauss(0.0, 0.2)
        elif u < 0.7:
            angle = math.pi / 2 + rng.gauss(0.0, 0.2)
        else:
            angle = rng.uniform(0, math.pi)
        length = 0.3 * (4.0 / 0.3) ** (rng.random() ** 2)  # skewed short
        return Scratch(rng.uniform(*z_range), rng.uniform(0, 2 * math.pi), angle, length,
                       rng.uniform(0.1, 0.18), rng.uniform(0.03, 0.065), rng.uniform(-0.12, 0.12) * length)

    c = cp.case
    body = ((c.groove_top or c.rim_thickness) + 0.3, c.length - 0.2)
    n = _poisson(rng, cond.fine_scratches * handling * _body_area(c) / REF_BODY)
    cp.case_scratches = [scratch(body) for _ in range(n)]
    if cp.kind in ("loaded", "bullet"):
        b = cp.bullet
        lo, hi = (cp.seat_depth if cp.kind == "loaded" else 0.0) + 0.3, b.length - 1.0
        if hi > lo:
            n = _poisson(rng, 0.5 * cond.fine_scratches * handling * _nose_area(cp) / REF_NOSE)
            cp.bullet_scratches = [scratch((lo, hi)) for _ in range(n)]


def _radius_at(profile, z: float) -> float:
    """Outer radius (mm) of a closed lathe profile at height ``z``."""
    best = 0.0
    for (r0, z0, _), (r1, z1, _) in zip(profile, profile[1:] + profile[:1]):
        if z0 != z1 and min(z0, z1) <= z <= max(z0, z1):
            best = max(best, r0 + (r1 - r0) * (z - z0) / (z1 - z0))
    return best


def _body_area(c: CaseSpec) -> float:
    """mm^2 of case wall above the extractor groove."""
    return math.pi * c.base_dia * (c.length - (c.groove_top or c.rim_thickness))


def _nose_area(cp: Copy) -> float:
    """mm^2 of bullet out in the open (all of it for a loose bullet), as a cylinder."""
    return math.pi * cp.bullet.dia * (cp.bullet.length - (cp.seat_depth if cp.kind == "loaded" else 0.0))


def _bullet_age(lot: Lot, jacket: str, rng: random.Random) -> float:
    """Tarnish on the bullet: set by its jacket, plus some of the lot's own age."""
    lo, hi = JACKET_AGE.get(jacket, (0.05, 0.4))
    x = rng.uniform(lo, hi)
    return 0.0 if lot.pristine else min(1.0, x + 0.4 * lot.age)


# ---------------------------------------------------------------- surface displacement


def _dent_offset(dents, r, z, theta):
    off = 0.0
    for d in dents:
        dth = (theta - d.theta + math.pi) % (2 * math.pi) - math.pi
        dist = math.hypot(dth * max(r, 0.5), z - d.z)
        if dist < d.radius:
            f = 1 - dist / d.radius
            off -= d.depth * (f * f if d.sharp else 0.5 * (1 + math.cos(math.pi * dist / d.radius)))
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
