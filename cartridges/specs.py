"""Cartridge and bullet specifications: load, fill defaults, validate.

* ``specs/*.toml``   one file per cartridge (case, loading, headstamp)
* ``bullets/*.toml`` one file per bullet; cartridges refer to bullets by key, so cartridges
  that take the same projectile (.308 Win and .300 BLK both use .308" bullets) share one
  definition

All lengths are millimetres, angles degrees. Case and bullet values are **maximum**
dimensions as published by SAAMI; each has a minus tolerance (``*_tol``): a real part lies
in ``[max - tol, max]``. Values a file doesn't give fall back to defaults (by cartridge
class for tolerances), and those fields are recorded in ``approx`` so the docs can mark
them as estimated.

Naming follows C.I.P./SAAMI drawings: L1 shoulder_start, L2 neck_start, L3 length,
P1 base_dia, P2 shoulder_dia, H1 mouth_dia (neck), R1 rim_dia, R rim_thickness,
E groove_top, E1 groove_dia, f rim_bevel, e groove_width, alpha rim_bevel_angle,
beta groove_front_angle.

Pure Python (no bpy): usable and testable outside Blender.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

_PKG = Path(__file__).resolve().parent
ROOT = _PKG.parent
# The packaged Blender extension carries its own copy of the specs in data/;
# in the repository they live at the top level.
_BUNDLED = _PKG / "data"
SPEC_DIR = _BUNDLED / "specs" if (_BUNDLED / "specs").is_dir() else ROOT / "specs"
BULLET_DIR = _BUNDLED / "bullets" if (_BUNDLED / "bullets").is_dir() else ROOT / "bullets"

CLASSES = ("pistol", "rifle", "rimfire")

# Primer cup diameter and primer pocket depth, mm. Typical industry values.
PRIMERS: dict[str, tuple[float, float]] = {
    "small-pistol": (4.45, 2.92),
    "large-pistol": (5.33, 2.97),
    "small-rifle": (4.45, 3.05),
    "large-rifle": (5.33, 3.30),
    "rimfire": (0.0, 0.0),
}

MAKERS_PATH = _BUNDLED / "makers.toml" if (_BUNDLED / "makers.toml").is_file() else ROOT / "makers.toml"

METALS = ("brass", "gilding-metal", "copper", "lead", "nickel", "steel", "steel-polymer", "steel-lacquer", "aluminum")
CRIMPS = ("none", "taper", "roll")

# SAAMI's usual cartridge tolerances by class (mm), used when a spec doesn't list one.
DEFAULT_TOL = {
    "pistol": {"length_tol": 0.25, "body_dia_tol": 0.18, "rim_dia_tol": 0.25, "rim_thickness_tol": 0.25, "groove_dia_tol": 0.51, "headspace_tol": 0.18},
    "rifle": {"length_tol": 0.51, "body_dia_tol": 0.20, "rim_dia_tol": 0.25, "rim_thickness_tol": 0.25, "groove_dia_tol": 0.51, "headspace_tol": 0.18},
    "rimfire": {"length_tol": 0.20, "body_dia_tol": 0.10, "rim_dia_tol": 0.30, "rim_thickness_tol": 0.18, "groove_dia_tol": 0.0, "headspace_tol": 0.0},
}
DEFAULT_CRIMP = {"pistol": ("taper", 0.08, 2.5), "rifle": ("none", 0.0, 0.0), "rimfire": ("roll", 0.10, 0.5)}


class SpecError(ValueError):
    pass


@dataclass
class CaseSpec:
    length: float  # L3, head to mouth
    base_dia: float  # P1, body diameter just above the extractor groove
    mouth_dia: float  # H1, neck diameter (bottleneck) or mouth diameter (straight)
    rim_dia: float  # R1
    rim_thickness: float  # R
    primer: str = "small-pistol"
    material: str = "brass"
    primer_cup: str = "brass"
    # Bottleneck cases only
    shoulder_dia: float | None = None  # P2
    shoulder_start: float | None = None  # L1, head to start of shoulder
    neck_start: float | None = None  # L2, head to start of neck
    shoulder_angle: float | None = None  # half-angle; used to derive neck_start if missing
    shoulder_radius: float = 0.64  # fillet where body meets shoulder
    neck_radius: float = 1.0  # fillet where shoulder meets neck
    # Extractor groove (rimless cases); defaults derived in finalize()
    groove_dia: float | None = None  # E1
    groove_top: float | None = None  # E, head to start of body; default from the groove below
    # Rim and groove shape (rimless cases), as SAAMI and C.I.P. draw it: the rim's outer face
    # runs from the head for (rim_thickness - rim_bevel), a bevel at rim_bevel_angle takes the
    # front edge in to the rim's flat front face at rim_thickness, then the groove bottom
    # (at least groove_width) and a ramp at groove_front_angle up to the body at groove_top.
    rim_bevel: float = 0.38  # C.I.P. f: axial length of the rim's front bevel (SAAMI: rim thickness minus rim land)
    rim_bevel_angle: float = 35.0  # C.I.P. alpha: rim front bevel, from the case axis
    groove_width: float = 0.90  # C.I.P. e: flat bottom of the extractor groove (.223: 0.76 minimum)
    groove_front_angle: float = 25.0  # C.I.P. beta: groove ramp up to the body, from the case axis
    head_chamfer: float = 0.15  # mm, the head-side edge of the rim; not in the standards, edge just broken
    # Construction details, not in standards
    mouth_wall: float = 0.30
    base_wall: float = 0.90
    web: float = 2.0  # solid head above the primer pocket (rimfire: head thickness)
    flash_hole_dia: float = 2.03  # Boxer, .080 in
    # Minus tolerances (mm). None = class default.
    length_tol: float | None = None
    body_dia_tol: float | None = None  # applies to base, shoulder and mouth diameters
    rim_dia_tol: float | None = None
    rim_thickness_tol: float | None = None
    groove_dia_tol: float | None = None
    headspace_tol: float | None = None  # moves the shoulder (L1 and L2 together)

    @property
    def rimfire(self) -> bool:
        return self.primer == "rimfire"

    @property
    def bottleneck(self) -> bool:
        return self.shoulder_dia is not None

    @property
    def rimless(self) -> bool:
        return not self.rimfire and self.rim_dia - self.base_dia < 0.4

    @property
    def primer_cup_dia(self) -> float:
        return PRIMERS[self.primer][0]

    @property
    def pocket_depth(self) -> float:
        return PRIMERS[self.primer][1]


@dataclass
class BulletSpec:
    key: str
    name: str
    dia: float  # maximum diameter
    length: float
    nose_length: float  # bearing surface to tip, along the axis
    tip: str = "round"  # round: jacket folded into a rounded tip; flat: flat meplat (flat point)
    tip_dia: float = 1.0  # round: diameter of the rounded tip; flat: meplat diameter
    weight_gr: float | None = None
    construction: str = "FMJ"
    boattail_length: float = 0.0
    boattail_angle: float = 0.0  # half-angle
    cannelure_z: float | None = None  # centre of the crimp groove, mm from the base
    cannelure_width: float = 1.0
    exposed_base: float = 0.0  # fraction of base radius showing the core (open-base FMJ)
    heel_dia: float | None = None  # heeled bullets (.22 LR): the part inside the case
    heel_length: float = 0.0
    jacket: str = "gilding-metal"
    core: str = "lead"
    dia_tol: float = 0.076  # SAAMI bullet diameter tolerance (.003 in)
    length_sd: float | None = None  # production spread; default 0.4% of length
    sources: dict[str, str] = field(default_factory=dict)
    approx: set[str] = field(default_factory=set)
    path: Path | None = None


@dataclass
class HeadstampSpec:
    """The cartridge's part of a headstamp; makers (``makers.toml``) supply the rest."""

    caliber: str = ""  # caliber marking as commercial makers stamp it ("223 REM")
    military: str = ""  # as military makers stamp it ("5.56"); default: caliber
    size: float | None = None  # letter height, mm; default from the head size


@dataclass
class Cartridge:
    key: str
    name: str
    cls: str  # pistol | rifle | rimfire
    case: CaseSpec
    bullet: BulletSpec
    oal_min: float  # SAAMI loaded length limits
    oal_max: float
    oal: float | None = None  # typical factory length (ignored when a roll crimp sits in a cannelure)
    oal_sd: float = 0.08  # production spread of loaded length
    crimp: str = "none"
    crimp_amount: float = 0.0  # reduction of the mouth's outside diameter
    crimp_length: float = 0.0  # length of case over which the crimp tapers in
    bullet_dia_max: float | None = None  # SAAMI maximum bullet diameter for this cartridge
    headstamp: HeadstampSpec = field(default_factory=HeadstampSpec)
    order: int = 100
    oal_note: str = ""
    sources: dict[str, str] = field(default_factory=dict)
    approx: set[str] = field(default_factory=set)
    path: Path | None = None

    def tol(self, name: str) -> float:
        v = getattr(self.case, name)
        return DEFAULT_TOL[self.cls][name] if v is None else v

    @property
    def seats_on_cannelure(self) -> bool:
        return self.crimp == "roll" and self.bullet.cannelure_z is not None and not self.bullet.heel_dia

    @property
    def seat_depth(self) -> float:
        """Nominal distance the bullet base sits below the case mouth."""
        b = self.bullet
        if b.heel_dia:
            return b.heel_length
        if self.seats_on_cannelure:
            return b.cannelure_z + 0.35  # mouth rolled into the groove, just above its centre
        return b.length - (self.oal - self.case.length)

    @property
    def nominal_oal(self) -> float:
        return self.case.length + self.bullet.length - self.seat_depth

    @property
    def max_dia(self) -> float:
        return max(self.case.rim_dia, self.case.base_dia, self.bullet.dia)


# ---------------------------------------------------------------- loading


def _build(cls, data: dict, where: str, approx: set[str], prefix: str, skip=("description",)):
    names = {f.name for f in fields(cls)}
    unknown = set(data) - names - {"approx"}
    if unknown:
        raise SpecError(f"{where}: unknown keys in [{prefix}]: {sorted(unknown)}")
    obj = cls(**{k: v for k, v in data.items() if k in names})
    for f in fields(cls):
        if f.name not in data and f.name not in skip:
            approx.add(f"{prefix}.{f.name}")
    for name in data.get("approx", []):
        approx.add(f"{prefix}.{name}")
    return obj


def load_bullet(path: Path) -> BulletSpec:
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    approx: set[str] = set()
    data.setdefault("key", path.stem)
    b = _build(BulletSpec, data, path.name, approx, "bullet", skip=("key", "name", "sources", "approx", "path"))
    b.approx = approx
    b.path = path
    w = b.key
    if b.tip not in ("round", "flat"):
        raise SpecError(f"{w}: tip must be 'round' or 'flat'")
    for metal in (b.jacket, b.core):
        if metal not in METALS:
            raise SpecError(f"{w}: unknown metal {metal!r}; use one of {METALS}")
    r, rt = b.dia / 2, b.tip_dia / 2
    if not (0 < rt < r):
        raise SpecError(f"{w}: tip_dia must be between 0 and dia")
    if b.tip == "round" and b.nose_length <= rt:
        raise SpecError(f"{w}: nose_length must be longer than the tip radius")
    if b.tip == "flat" and b.nose_length < r - rt:
        raise SpecError(f"{w}: nose_length too short for a tangent ogive")
    if b.nose_length + b.boattail_length >= b.length:
        raise SpecError(f"{w}: nose and boat tail are longer than the bullet")
    if b.cannelure_z is not None and not (b.boattail_length + b.cannelure_width / 2 < b.cannelure_z < b.length - b.nose_length):
        raise SpecError(f"{w}: cannelure must sit on the bearing surface")
    if b.heel_dia is not None and (b.heel_dia >= b.dia or b.heel_length <= 0):
        raise SpecError(f"{w}: heel_dia must be under dia, with a heel_length")
    if b.length_sd is None:
        b.length_sd = round(0.004 * b.length, 3)
    return b


def load_bullets(bullet_dir: Path = BULLET_DIR) -> dict[str, BulletSpec]:
    return {b.key: b for b in (load_bullet(p) for p in sorted(bullet_dir.glob("*.toml")))}


def finalize(c: Cartridge) -> Cartridge:
    k, w = c.case, c.key
    if c.cls not in CLASSES:
        raise SpecError(f"{w}: class must be one of {CLASSES}")
    if k.primer not in PRIMERS:
        raise SpecError(f"{w}: unknown primer {k.primer!r}; use one of {sorted(PRIMERS)}")
    for metal in (k.material, k.primer_cup):
        if metal not in METALS:
            raise SpecError(f"{w}: unknown metal {metal!r}; use one of {METALS}")
    if c.crimp not in CRIMPS:
        raise SpecError(f"{w}: crimp must be one of {CRIMPS}")

    if k.bottleneck:
        if k.shoulder_start is None:
            raise SpecError(f"{w}: bottleneck case needs shoulder_start (L1)")
        if k.neck_start is None:
            if k.shoulder_angle is None:
                raise SpecError(f"{w}: give neck_start (L2) or shoulder_angle")
            drop = (k.shoulder_dia - k.mouth_dia) / 2
            k.neck_start = round(k.shoulder_start + drop / math.tan(math.radians(k.shoulder_angle)), 3)
            c.approx.add("case.neck_start(derived)")
        if not (k.mouth_dia < k.shoulder_dia <= k.base_dia):
            raise SpecError(f"{w}: need mouth_dia < shoulder_dia <= base_dia")
        if not (0 < k.shoulder_start < k.neck_start < k.length):
            raise SpecError(f"{w}: need 0 < shoulder_start < neck_start < length")
    if k.rimless:
        if k.groove_dia is None:
            k.groove_dia = round(k.rim_dia * 0.86, 2)
        if not (0.0 <= k.rim_bevel < k.rim_thickness):
            raise SpecError(f"{w}: rim_bevel must be shorter than the rim thickness")
        if k.groove_top is None:  # C.I.P.: E = R + e + ramp
            ramp = (k.base_dia - k.groove_dia) / 2 / math.tan(math.radians(k.groove_front_angle))
            k.groove_top = round(k.rim_thickness + k.groove_width + ramp, 2)
        if not (k.groove_dia < k.base_dia and k.groove_top > k.rim_thickness):
            raise SpecError(f"{w}: extractor groove must be narrower than the body and above the rim")
    # tolerances: record which ones fell back to class defaults
    for name in DEFAULT_TOL[c.cls]:
        if getattr(k, name) is None:
            c.approx.add(f"case.{name}")

    b = c.bullet
    if c.bullet_dia_max is not None and b.dia > c.bullet_dia_max + 1e-6:
        raise SpecError(f"{w}: bullet {b.key} ({b.dia} mm) is over this cartridge's maximum bullet diameter {c.bullet_dia_max}")
    if b.heel_dia is not None and b.heel_dia > k.mouth_dia - 2 * k.mouth_wall + 1e-6:
        raise SpecError(f"{w}: bullet heel must fit inside the case mouth")
    if not c.seats_on_cannelure and not b.heel_dia and c.oal is None:
        raise SpecError(f"{w}: [loaded] needs oal unless the bullet is roll-crimped into a cannelure")
    head = k.web if k.rimfire else k.pocket_depth + k.web
    if not (0.5 < c.seat_depth < k.length - head):
        raise SpecError(f"{w}: seat depth {c.seat_depth:.2f} mm is outside the case; check bullet, oal and case length")
    if not (c.oal_min - 1e-6 <= c.nominal_oal <= c.oal_max + 1e-6):
        raise SpecError(f"{w}: loaded length {c.nominal_oal:.2f} is outside {c.oal_min}-{c.oal_max}")
    if c.oal_min >= c.oal_max:
        raise SpecError(f"{w}: oal_min must be under oal_max")
    return c


def load(path: Path, bullets: dict[str, BulletSpec] | None = None) -> Cartridge:
    bullets = load_bullets() if bullets is None else bullets
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    where = path.name
    for section in ("case", "loaded"):
        if section not in data:
            raise SpecError(f"{where}: missing [{section}] section")
    cls = data.get("class")
    if cls not in CLASSES:
        raise SpecError(f"{where}: class must be one of {CLASSES}")
    approx: set[str] = set()
    case = _build(CaseSpec, data["case"], where, approx, "case")
    loaded = dict(data["loaded"])
    bkey = loaded.pop("bullet", None)
    if bkey not in bullets:
        raise SpecError(f"{where}: [loaded] bullet {bkey!r} not found in bullets/; have {sorted(bullets)}")
    crimp_default = DEFAULT_CRIMP[cls]
    known = {"oal", "oal_min", "oal_max", "oal_sd", "crimp", "crimp_amount", "crimp_length", "bullet_dia_max", "note", "approx"}
    unknown = set(loaded) - known
    if unknown:
        raise SpecError(f"{where}: unknown keys in [loaded]: {sorted(unknown)}")
    for need in ("oal_min", "oal_max"):
        if need not in loaded:
            raise SpecError(f"{where}: [loaded] needs {need}")
    for name in ("crimp_amount", "crimp_length", "oal_sd"):
        if name not in loaded:
            approx.add(f"loaded.{name}")
    for name in loaded.get("approx", []):
        approx.add(f"loaded.{name}")
    c = Cartridge(
        key=data.get("key", path.stem),
        name=data["name"],
        cls=cls,
        case=case,
        bullet=bullets[bkey],
        oal=loaded.get("oal"),
        oal_min=loaded["oal_min"],
        oal_max=loaded["oal_max"],
        oal_sd=loaded.get("oal_sd", 0.08 if cls == "pistol" else 0.06),
        crimp=loaded.get("crimp", crimp_default[0]),
        crimp_amount=loaded.get("crimp_amount", crimp_default[1]),
        crimp_length=loaded.get("crimp_length", crimp_default[2]),
        bullet_dia_max=loaded.get("bullet_dia_max"),
        oal_note=loaded.get("note", ""),
        headstamp=HeadstampSpec(**data.get("headstamp", {})),
        order=data.get("order", 100),
        sources=data.get("sources", {}),
        approx=approx,
        path=path,
    )
    return finalize(c)


# ---------------------------------------------------------------- makers

SYMBOLS = ("nato", "ring", "dot")
PRIMER_CRIMPS = ("none", "ring", "stakes")
PLACEHOLDERS = {"caliber": "C", "military": "M", "yy": "00", "code": "0"}


@dataclass
class Mark:
    text: str = ""
    symbol: str = ""
    at: float = 12.0  # clock position; 0 = centre (rimfire)


@dataclass
class Style:
    weight: float = 0.0  # stroke growth per side, fraction of letter height
    width: float = 1.0
    size: float = 1.0
    depth: float = 1.0


@dataclass
class Maker:
    """A headstamp layout plus the finishes that go with it (see ``makers.toml``)."""

    key: str
    name: str
    marks: list[Mark]
    classes: list[str] = field(default_factory=list)
    weight: float = 1.0
    weights: dict[str, float] = field(default_factory=dict)
    case: dict[str, float] = field(default_factory=lambda: {"brass": 1.0})
    primer: dict[str, float] = field(default_factory=dict)  # empty: the spec's primer cup
    sealant: dict[str, float] = field(default_factory=lambda: {"none": 1.0})
    smear: tuple[float, float] = (0.0, 0.0)
    primer_crimp: str = "none"
    dots: tuple[int, int] = (0, 0)
    years: tuple[int, int] = (1990, 2026)
    codes: list[str] = field(default_factory=list)
    anneal: tuple[float, float] = (0.05, 0.35)
    age: tuple[float, float] = (0.0, 0.4)
    jacket: dict[str, float] = field(default_factory=dict)  # empty: the bullet's own
    tip: dict[str, float] = field(default_factory=lambda: {"none": 1.0})
    style: Style = field(default_factory=Style)

    def weight_for(self, cart: Cartridge) -> float:
        if cart.key in self.weights:
            return self.weights[cart.key]
        return self.weight if cart.cls in self.classes else 0.0


@dataclass
class Makers:
    makers: dict[str, Maker]
    sealants: dict[str, tuple[float, float, float]]
    paints: dict[str, tuple[float, float, float]]

    def for_cartridge(self, cart: Cartridge) -> dict[str, float]:
        """{maker key: weight} of the makers that load ``cart``."""
        return {k: w for k, m in self.makers.items() if (w := m.weight_for(cart)) > 0}


def _rgb_table(data, where, name):
    out = {}
    for k, v in data.get(name, {}).items():
        if not (isinstance(v, list) and len(v) == 3 and all(0 <= x <= 1 for x in v)):
            raise SpecError(f"{where}: [{name}] {k} must be [r, g, b] in 0-1")
        out[k] = tuple(v)
    return out


def load_makers(path: Path = MAKERS_PATH, cartridges: set[str] | None = None) -> Makers:
    """Load and check ``makers.toml``. ``cartridges``: known keys, to catch typos in ``weights``."""
    where = path.name
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    sealants, paints = _rgb_table(data, where, "sealants"), _rgb_table(data, where, "paints")
    makers = {}
    for raw in data.get("maker", []):
        raw = dict(raw)
        key = raw.get("key")
        if not key or key in makers:
            raise SpecError(f"{where}: every [[maker]] needs a unique key (got {key!r})")
        w = f"{where} maker {key}"
        names = {f.name for f in fields(Maker)}
        unknown = set(raw) - names
        if unknown:
            raise SpecError(f"{w}: unknown keys {sorted(unknown)}")
        marks = []
        for m in raw.pop("marks", []):
            mk = Mark(**m)
            if bool(mk.text) == bool(mk.symbol):
                raise SpecError(f"{w}: each mark needs text or symbol")
            if mk.symbol and mk.symbol not in SYMBOLS:
                raise SpecError(f"{w}: unknown symbol {mk.symbol!r}; use one of {SYMBOLS}")
            if not 0 <= mk.at <= 12:
                raise SpecError(f"{w}: mark position 'at' is a clock position, 0-12")
            try:
                mk.text.format(**PLACEHOLDERS)
            except (KeyError, IndexError, ValueError) as e:
                raise SpecError(f"{w}: bad placeholder in {mk.text!r}; use {sorted(PLACEHOLDERS)}") from e
            marks.append(mk)
        if not marks:
            raise SpecError(f"{w}: needs at least one mark")
        style = Style(**raw.pop("style", {}))
        for name in ("smear", "dots", "years", "anneal", "age"):
            if name in raw:
                raw[name] = tuple(raw[name])
        mk = Maker(marks=marks, style=style, **raw)
        bad = [c for c in mk.classes if c not in CLASSES]
        if bad:
            raise SpecError(f"{w}: unknown classes {bad}")
        for metal in [*mk.case, *mk.primer, *mk.jacket]:
            if metal not in METALS:
                raise SpecError(f"{w}: unknown metal {metal!r}; use one of {METALS}")
        for s in mk.sealant:
            if s != "none" and s not in sealants:
                raise SpecError(f"{w}: sealant {s!r} isn't in [sealants]")
        for t in mk.tip:
            if t != "none" and t not in paints:
                raise SpecError(f"{w}: tip paint {t!r} isn't in [paints]")
        if mk.primer_crimp not in PRIMER_CRIMPS:
            raise SpecError(f"{w}: primer_crimp must be one of {PRIMER_CRIMPS}")
        if "{code}" in "".join(m.text for m in marks) and not mk.codes:
            raise SpecError(f"{w}: uses {{code}} but has no codes")
        if cartridges is not None:
            unknown = set(mk.weights) - cartridges
            if unknown:
                raise SpecError(f"{w}: weights name unknown cartridges {sorted(unknown)}")
        makers[key] = mk
    return Makers(makers, sealants, paints)


_default_makers: Makers | None = None


def default_makers() -> Makers:
    """``makers.toml`` next to the specs, loaded once."""
    global _default_makers
    if _default_makers is None:
        _default_makers = load_makers(MAKERS_PATH, {p.stem for p in SPEC_DIR.glob("*.toml")})
    return _default_makers


def load_all(spec_dir: Path = SPEC_DIR, keys: list[str] | None = None) -> list[Cartridge]:
    bullets = load_bullets()
    carts = [load(p, bullets) for p in sorted(spec_dir.glob("*.toml"))]
    carts.sort(key=lambda c: (c.order, c.key))
    if keys:
        by_key = {c.key: c for c in carts}
        missing = [k for k in keys if k not in by_key]
        if missing:
            raise SpecError(f"no spec for {missing}; have {sorted(by_key)}")
        carts = [by_key[k] for k in keys]
    return carts
