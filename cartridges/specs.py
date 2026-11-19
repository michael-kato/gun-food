"""Cartridge specifications: load, fill defaults, validate.

Every cartridge is one TOML file in ``specs/``. All lengths are millimetres,
angles are degrees. Values the file does not give fall back to typical
defaults below, and those fields are recorded in ``Cartridge.approx`` so the
generated docs can mark them as approximate.

Naming follows C.I.P. drawings where one exists:
  L1 shoulder_start, L2 neck_start, L3 case length, L6 overall length,
  P1 base_dia, P2 shoulder_dia, H1 mouth_dia (neck), R1 rim_dia,
  R rim_thickness, E groove_top, E1 groove_dia.

This module is pure Python (no bpy) so it can be tested and used outside Blender.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

SPEC_DIR = Path(__file__).resolve().parent.parent / "specs"

# Primer cup diameter and primer pocket depth, mm. Typical industry values.
PRIMERS: dict[str, tuple[float, float]] = {
    "small-pistol": (4.45, 2.92),  # .175 in cup, .115 in pocket
    "large-pistol": (5.33, 2.97),  # .210 in cup, .117 in pocket
    "small-rifle": (4.45, 3.05),  # .175 in cup, .120 in pocket
    "large-rifle": (5.33, 3.30),  # .210 in cup, .130 in pocket
    "rimfire": (0.0, 0.0),  # priming compound sits inside the folded rim
}

METALS = ("brass", "gilding-metal", "copper", "lead", "nickel", "steel", "aluminum")


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
    primer_cup: str = "brass"  # primer cup metal (brass or nickel are common)
    # Bottleneck cases only
    shoulder_dia: float | None = None  # P2
    shoulder_start: float | None = None  # L1, head to start of shoulder
    neck_start: float | None = None  # L2, head to start of neck
    shoulder_angle: float | None = None  # half-angle; used to derive neck_start if missing
    shoulder_radius: float = 0.64  # fillet where body meets shoulder (C.I.P. r1 min)
    neck_radius: float = 1.0  # fillet where shoulder meets neck (C.I.P. r2)
    # Extractor groove (rimless cases). Defaults are derived in finalize().
    groove_dia: float | None = None  # E1
    groove_top: float | None = None  # E, head to start of body
    rim_bevel_angle: float = 35.0  # rim front bevel, from the radial plane
    groove_front_angle: float = 25.0  # groove ramp up to the body, from the axis
    # Construction details, not in standards
    mouth_wall: float = 0.30
    base_wall: float = 0.90  # wall thickness just above the web
    web: float = 2.0  # solid head above the primer pocket (rimfire: head thickness)
    flash_hole_dia: float = 2.03  # Boxer, .080 in

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
    dia: float
    length: float
    nose_length: float  # bearing surface to tip, along the axis
    meplat_dia: float = 0.0  # flat at the tip; 0 = pointed
    description: str = ""
    boattail_length: float = 0.0
    boattail_angle: float = 0.0  # half-angle
    cannelure: bool = False  # crimp groove at the case mouth
    cannelure_width: float = 1.0
    exposed_base: float = 0.0  # fraction of base radius showing the core (open-base FMJ)
    heel_dia: float | None = None  # heeled bullets (.22 LR): part inside the case
    jacket: str = "gilding-metal"
    core: str = "lead"


@dataclass
class HeadstampSpec:
    top: str = ""  # arc above the primer, letters' bottoms toward the centre
    bottom: str = ""  # arc below the primer, upright
    center: str = ""  # rimfire: raised mark in the middle of the head
    size: float | None = None  # letter height; default from head size


@dataclass
class Cartridge:
    key: str
    name: str
    case: CaseSpec
    bullet: BulletSpec
    oal: float  # L6, loaded overall length
    headstamp: HeadstampSpec = field(default_factory=HeadstampSpec)
    order: int = 100
    oal_note: str = ""
    sources: dict[str, str] = field(default_factory=dict)
    approx: set[str] = field(default_factory=set)  # dotted names of defaulted/estimated values
    path: Path | None = None

    @property
    def seat_depth(self) -> float:
        """How far the bullet base sits below the case mouth."""
        return self.bullet.length - (self.oal - self.case.length)

    @property
    def max_dia(self) -> float:
        return max(self.case.rim_dia, self.case.base_dia, self.bullet.dia)


def _build(cls, data: dict, where: str, approx: set[str], prefix: str):
    names = {f.name for f in fields(cls)}
    unknown = set(data) - names - {"approx"}
    if unknown:
        raise SpecError(f"{where}: unknown keys in [{prefix}]: {sorted(unknown)}")
    obj = cls(**{k: v for k, v in data.items() if k in names})
    for f in fields(cls):
        if f.name not in data and f.name not in ("description",):
            approx.add(f"{prefix}.{f.name}")
    for name in data.get("approx", []):
        approx.add(f"{prefix}.{name}")
    return obj


def finalize(c: Cartridge) -> Cartridge:
    """Derive dependent values and validate. Raises SpecError on bad input."""
    k = c.case
    w = c.key
    if k.primer not in PRIMERS:
        raise SpecError(f"{w}: unknown primer {k.primer!r}; use one of {sorted(PRIMERS)}")
    for metal in (k.material, k.primer_cup, c.bullet.jacket, c.bullet.core):
        if metal not in METALS:
            raise SpecError(f"{w}: unknown metal {metal!r}; use one of {METALS}")

    if k.bottleneck:
        if k.shoulder_start is None:
            raise SpecError(f"{w}: bottleneck case needs shoulder_start (L1)")
        if k.neck_start is None:
            if k.shoulder_angle is None:
                raise SpecError(f"{w}: give neck_start (L2) or shoulder_angle")
            drop = (k.shoulder_dia - k.mouth_dia) / 2
            k.neck_start = round(k.shoulder_start + drop / math.tan(math.radians(k.shoulder_angle)), 3)
            c.approx.discard("case.neck_start")
            c.approx.add("case.neck_start(derived)")
        if not (k.mouth_dia < k.shoulder_dia <= k.base_dia):
            raise SpecError(f"{w}: need mouth_dia < shoulder_dia <= base_dia")
        if not (0 < k.shoulder_start < k.neck_start < k.length):
            raise SpecError(f"{w}: need 0 < shoulder_start < neck_start < length")
    else:
        for name in ("shoulder_start", "neck_start", "shoulder_angle"):
            c.approx.discard(f"case.{name}")
        c.approx.discard("case.shoulder_dia")

    if k.rimless:
        if k.groove_dia is None:
            k.groove_dia = round(k.rim_dia * 0.86, 2)
        if k.groove_top is None:
            k.groove_top = round(k.rim_thickness + 1.9, 2)
        if not (k.groove_dia < k.base_dia and k.groove_top > k.rim_thickness):
            raise SpecError(f"{w}: extractor groove must be narrower than the body and above the rim")
    else:
        for name in ("groove_dia", "groove_top", "rim_bevel_angle", "groove_front_angle"):
            c.approx.discard(f"case.{name}")

    b = c.bullet
    if b.meplat_dia >= b.dia:
        raise SpecError(f"{w}: meplat_dia must be smaller than dia")
    if b.nose_length < (b.dia - b.meplat_dia) / 2:
        raise SpecError(f"{w}: nose_length too short for a tangent ogive")
    if b.nose_length + b.boattail_length >= b.length:
        raise SpecError(f"{w}: nose and boat tail are longer than the bullet")

    head = k.web if k.rimfire else k.pocket_depth + k.web
    if not (0.5 < c.seat_depth < k.length - head):
        raise SpecError(
            f"{w}: seat depth {c.seat_depth:.2f} mm is outside the case; check bullet.length, oal and case.length"
        )
    if b.heel_dia is not None and b.heel_dia > k.mouth_dia - 2 * k.mouth_wall + 1e-6:
        raise SpecError(f"{w}: heel_dia must fit inside the case mouth")
    if b.cannelure and c.seat_depth - b.cannelure_width < b.boattail_length:
        raise SpecError(f"{w}: cannelure overlaps the boat tail")
    if c.oal <= k.length:
        raise SpecError(f"{w}: oal must be longer than the case")
    return c


def load(path: Path) -> Cartridge:
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    where = path.name
    approx: set[str] = set()
    for section in ("case", "bullet", "loaded"):
        if section not in data:
            raise SpecError(f"{where}: missing [{section}] section")
    case = _build(CaseSpec, data["case"], where, approx, "case")
    bullet = _build(BulletSpec, data["bullet"], where, approx, "bullet")
    headstamp = HeadstampSpec(**data.get("headstamp", {}))
    loaded = data["loaded"]
    if "oal" not in loaded:
        raise SpecError(f"{where}: [loaded] needs oal")
    c = Cartridge(
        key=data.get("key", path.stem),
        name=data["name"],
        case=case,
        bullet=bullet,
        oal=loaded["oal"],
        oal_note=loaded.get("note", ""),
        headstamp=headstamp,
        order=data.get("order", 100),
        sources=data.get("sources", {}),
        approx=approx,
        path=path,
    )
    return finalize(c)


def load_all(spec_dir: Path = SPEC_DIR, keys: list[str] | None = None) -> list[Cartridge]:
    carts = [load(p) for p in sorted(spec_dir.glob("*.toml"))]
    carts.sort(key=lambda c: (c.order, c.key))
    if keys:
        by_key = {c.key: c for c in carts}
        missing = [k for k in keys if k not in by_key]
        if missing:
            raise SpecError(f"no spec for {missing}; have {sorted(by_key)}")
        carts = [by_key[k] for k in keys]
    return carts
