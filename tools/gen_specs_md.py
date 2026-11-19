"""Regenerate SPECS.md from specs/*.toml.

    python tools/gen_specs_md.py           # write SPECS.md
    python tools/gen_specs_md.py --check   # exit 1 if SPECS.md is out of date
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cartridges import specs  # noqa: E402

OUT = ROOT / "SPECS.md"

CASE_ROWS = [
    ("length", "Case length (L3)"),
    ("base_dia", "Base diameter (P1)"),
    ("mouth_dia", "Neck / mouth diameter (H1)"),
    ("rim_dia", "Rim diameter (R1)"),
    ("rim_thickness", "Rim thickness (R)"),
    ("shoulder_dia", "Shoulder diameter (P2)"),
    ("shoulder_start", "Head to shoulder (L1)"),
    ("neck_start", "Head to neck (L2)"),
    ("shoulder_angle", "Shoulder half-angle (°)"),
    ("groove_dia", "Extractor groove diameter (E1)"),
    ("groove_top", "Head to body (E)"),
]
BULLET_ROWS = [
    ("dia", "Bullet diameter"),
    ("length", "Bullet length"),
    ("nose_length", "Nose (ogive) length"),
    ("meplat_dia", "Meplat diameter"),
    ("boattail_length", "Boat-tail length"),
    ("boattail_angle", "Boat-tail half-angle (°)"),
]


def _num(v):
    return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def _case_cell(c, name):
    k = c.case
    if name in ("shoulder_dia", "shoulder_start", "neck_start", "shoulder_angle") and not k.bottleneck:
        return "—"
    if name in ("groove_dia", "groove_top") and not k.rimless:
        return "—"
    v = getattr(k, name)
    if v is None:
        if name == "shoulder_angle":
            import math

            v = math.degrees(math.atan((k.shoulder_dia - k.mouth_dia) / 2 / (k.neck_start - k.shoulder_start)))
            return f"{v:.1f}†"
        return "—"
    s = _num(v)
    if name == "neck_start" and "case.neck_start(derived)" in c.approx:
        return s + "†"
    if f"case.{name}" in c.approx:
        return "≈" + s
    return s


def _bullet_cell(c, name):
    v = getattr(c.bullet, name)
    if not v:
        return "—"
    return _num(v)


def generate() -> str:
    carts = specs.load_all()
    head = "| | " + " | ".join(c.name for c in carts) + " |"
    sep = "|---|" + "---|" * len(carts)
    out = [
        "# Cartridge specifications",
        "",
        "<!-- Generated from specs/*.toml by `python tools/gen_specs_md.py`. Do not edit by hand. -->",
        "",
        "All values are millimetres. Case and overall-length values are **maximum cartridge dimensions**",
        "from C.I.P./SAAMI data (see sources below), which is what the models are built to. Real cases",
        "measure slightly under these.",
        "",
        "- **≈** estimated or typical value, not from a standard",
        "- **†** derived from the stated shoulder angle",
        "- **—** does not apply",
        "",
        "## Cases",
        "",
        head,
        sep,
    ]
    for name, label in CASE_ROWS:
        out.append(f"| {label} | " + " | ".join(_case_cell(c, name) for c in carts) + " |")
    out.append("| Primer | " + " | ".join(c.case.primer for c in carts) + " |")
    out += ["", "## Loaded rounds", "", head, sep]
    out.append("| Overall length (L6) | " + " | ".join(_num(c.oal) + ("*" if c.oal_note else "") for c in carts) + " |")
    out.append("| Bullet seating depth | " + " | ".join(f"{c.seat_depth:.2f}" for c in carts) + " |")
    out += ["", "\\* see the cartridge's notes below.", ""]
    out += [
        "## Bullets",
        "",
        "Bullets are **typical factory bullets, not standards**: bullet shape varies by load. Diameters follow the standard.",
        "",
        head,
        sep,
        "| Bullet | " + " | ".join(c.bullet.description or "—" for c in carts) + " |",
    ]
    for name, label in BULLET_ROWS:
        out.append(f"| {label} | " + " | ".join(_bullet_cell(c, name) for c in carts) + " |")
    out += ["", "## Sources and notes", ""]
    for c in carts:
        out.append(f"### {c.name}")
        out.append("")
        out.append(f"Spec file: [`specs/{c.path.name}`](specs/{c.path.name})")
        out.append("")
        for k, v in c.sources.items():
            out.append(f"- **{k}:** {v}")
        if c.oal_note:
            out.append(f"- **overall length note:** {c.oal_note}")
        est = sorted(n.split(".", 1)[1] for n in c.approx if n.startswith("case.") and n.split(".", 1)[1] in {r for r, _ in CASE_ROWS})
        est = [e for e in est if _case_cell(c, e) != "—" and not _case_cell(c, e).endswith("†")]
        if est:
            out.append(f"- **estimated case values:** {', '.join(est)}")
        out.append("")
    return "\n".join(out)


def main(argv):
    text = generate()
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("SPECS.md is out of date: run python tools/gen_specs_md.py")
            return 1
        print("SPECS.md is up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
