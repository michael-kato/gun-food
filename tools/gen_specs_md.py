"""Regenerate SPECS.md from specs/*.toml and bullets/*.toml.

    python tools/gen_specs_md.py           # write SPECS.md
    python tools/gen_specs_md.py --check   # exit 1 if SPECS.md is out of date
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cartridges import specs, variation  # noqa: E402

OUT = ROOT / "SPECS.md"

CASE_ROWS = [
    # (field, label, tolerance field)
    ("length", "Case length (L3)", "length_tol"),
    ("base_dia", "Base diameter (P1)", "body_dia_tol"),
    ("shoulder_dia", "Shoulder diameter (P2)", "body_dia_tol"),
    ("mouth_dia", "Neck / mouth diameter (H1)", "body_dia_tol"),
    ("shoulder_start", "Head to shoulder (L1)", "headspace_tol"),
    ("neck_start", "Head to neck (L2)", "headspace_tol"),
    ("rim_dia", "Rim diameter (R1)", "rim_dia_tol"),
    ("rim_thickness", "Rim thickness (R)", "rim_thickness_tol"),
    ("groove_dia", "Extractor groove diameter (E1)", "groove_dia_tol"),
    ("groove_top", "Head to body (E)", None),
]
BULLET_ROWS = [
    ("dia", "Diameter (max)"),
    ("length", "Length"),
    ("nose_length", "Nose (ogive) length"),
    ("tip_dia", "Tip diameter"),
    ("boattail_length", "Boat-tail length"),
    ("boattail_angle", "Boat-tail half-angle (°)"),
    ("cannelure_z", "Cannelure, from base"),
    ("heel_length", "Heel length"),
]


def _num(v):
    return f"{v:.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def _applies(c, name):
    k = c.case
    if name in ("shoulder_dia", "shoulder_start", "neck_start") and not k.bottleneck:
        return False
    if name in ("groove_dia", "groove_top") and not k.rimless:
        return False
    return True


def _case_cell(c, name, tol_name):
    if not _applies(c, name):
        return "—"
    s = _num(getattr(c.case, name))
    if f"case.{name}" in c.approx:
        s = "≈" + s
    if name == "neck_start" and "case.neck_start(derived)" in c.approx:
        s += "†"
    if tol_name:
        t = c.tol(tol_name)
        if t:
            s += f" −{_num(t)}" + ("≈" if f"case.{tol_name}" in c.approx else "")
    return s


def _choices(table: dict) -> str:
    total = sum(table.values()) or 1
    return ", ".join(f"{k} {w / total:.0%}" if len(table) > 1 else k for k, w in table.items())


def _makers_section(carts) -> list[str]:
    makers = specs.default_makers()
    out = [
        "## Makers",
        "",
        "Each copy draws a maker ([`makers.toml`](makers.toml)), weighted per cartridge. The maker",
        "sets the headstamp, case and primer finish, primer sealant, primer crimp, annealing stain,",
        "age and, on loaded rounds, bullet jacket and tip paint. Commercial marks are made up; `LC`",
        "is the US Army's Lake City plant; the Eastern-bloc numbers are arsenal codes.",
        "",
        "| Maker | Headstamp | Case | Primer | Sealant | Primer crimp | Tip | Share per cartridge |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key, m in makers.makers.items():
        marks = " · ".join(f"`{mk.text}`@{mk.at:g}" if mk.text else f"⟨{mk.symbol}⟩@{mk.at:g}" for mk in m.marks)
        if m.dots[1]:
            marks += f" + {m.dots[0]}–{m.dots[1]} dots"
        share = []
        for c in carts:
            table = makers.for_cartridge(c)
            if key in table:
                share.append(f"{c.key} {table[key] / sum(table.values()):.0%}")
        out.append(
            f"| **{key}**<br>{m.name} | {marks} | {_choices(m.case)} | {_choices(m.primer) if m.primer else 'spec'} | "
            f"{_choices(m.sealant)} | {m.primer_crimp} | {_choices(m.tip)} | {', '.join(share) or '—'} |"
        )
    out += [
        "",
        "Tip paint goes on loaded rounds only. Annealing stains show on brass bottleneck cases only.",
        "",
    ]
    return out


def generate() -> str:
    carts = specs.load_all()
    bullets = specs.load_bullets()
    head = "| | " + " | ".join(c.name for c in carts) + " |"
    sep = "|---|" + "---|" * len(carts)
    out = [
        "# Cartridge specifications",
        "",
        "<!-- Generated from specs/*.toml and bullets/*.toml by `python tools/gen_specs_md.py`. Do not edit by hand. -->",
        "",
        "All values are millimetres. Case values are **SAAMI maximum cartridge dimensions** with",
        "SAAMI's minus tolerance: `19.15 −0.25` means a real case measures between 18.90 and 19.15.",
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
    for name, label, tol_name in CASE_ROWS:
        out.append(f"| {label} | " + " | ".join(_case_cell(c, name, tol_name) for c in carts) + " |")
    out.append("| Primer | " + " | ".join(c.case.primer for c in carts) + " |")

    out += ["", "## Loaded rounds", "", head, sep]
    out.append("| Bullet | " + " | ".join(f"[`{c.bullet.key}`](#{c.bullet.key})" for c in carts) + " |")
    out.append("| Overall length, SAAMI min–max | " + " | ".join(f"{_num(c.oal_min)}–{_num(c.oal_max)}" for c in carts) + " |")
    out.append(
        "| Overall length, as built | "
        + " | ".join(f"{c.nominal_oal:.2f}" + (" (cannelure)" if c.seats_on_cannelure else "") + ("*" if c.oal_note else "") for c in carts)
        + " |"
    )
    out.append("| Seating depth | " + " | ".join(f"{c.seat_depth:.2f}" for c in carts) + " |")
    out.append("| Crimp | " + " | ".join(c.crimp if c.crimp == "none" else f"{c.crimp}, ≈{_num(c.crimp_amount)} on dia" for c in carts) + " |")
    out.append("| Maximum bullet diameter | " + " | ".join(_num(c.bullet_dia_max) if c.bullet_dia_max else "—" for c in carts) + " |")
    out += [
        "",
        "Roll-crimped rounds seat with the case mouth in the bullet's cannelure, so their length follows the",
        "bullet. Taper-crimped pistol rounds use a typical factory length. Crimp amounts are typical values",
        "from reloading references, not standards.",
        "",
    ]

    bl = sorted(bullets.values(), key=lambda b: b.key)
    users = {b.key: [c.name for c in carts if c.bullet.key == b.key] for b in bl}
    out += [
        "## Bullets",
        "",
        "Bullets live in `bullets/` and are shared: any cartridge can load any bullet that fits. Diameters",
        "are SAAMI maximums with SAAMI's tolerance; **shapes are typical factory bullets, not standards**.",
        "",
        "| | " + " | ".join(f'<a id="{b.key}"></a>`{b.key}`' for b in bl) + " |",
        "|---|" + "---|" * len(bl),
        "| Bullet | " + " | ".join(b.name for b in bl) + " |",
        "| Used by | " + " | ".join(", ".join(users[b.key]) or "—" for b in bl) + " |",
        "| Tip | " + " | ".join(b.tip for b in bl) + " |",
    ]
    for name, label in BULLET_ROWS:
        cells = []
        for b in bl:
            v = getattr(b, name)
            if not v:
                cells.append("—")
            elif name == "dia":
                cells.append(f"{_num(v)} −{_num(b.dia_tol)}")
            elif name == "length":
                cells.append(f"{_num(v)} ±{_num(2 * b.length_sd)}")
            else:
                cells.append(_num(v))
        out.append(f"| {label} | " + " | ".join(cells) + " |")

    cond = variation.CONDITIONS["new"]
    fired = variation.CONDITIONS["fired"]
    out += [
        "",
        "## Variation between copies",
        "",
        "Every copy in the scene is a separate, seeded sample of its spec (`cartridges/variation.py`):",
        "",
        "- Dimensions are drawn inside the SAAMI band. Real parts don't fill the band evenly, so samples",
        "  cluster at these fractions of the band below max (mean, standard deviation), inferred from",
        "  reloading-forum lot measurements:",
        "",
        "  | Group | Mean | SD |",
        "  |---|---|---|",
    ]
    for k, (m, sd) in variation.PROCESS.items():
        out.append(f"  | {k} | {m:.2f} | {sd:.2f} |")
    out += [
        "",
        "- Loaded length varies with a 0.08 mm (pistol) / 0.06 mm (rifle) standard deviation, clamped to",
        "  SAAMI's limits. Bullet length varies 0.4% (one SD).",
        f"- Factory-new handling damage: about {cond.dents_per_10mm:g} dents per 10 mm of case, "
        f"{_num(cond.dent_depth[0])}–{_num(cond.dent_depth[1])} mm deep; up to {_num(cond.ovality[1])} mm out-of-round at the mouth;",
        f"  a {cond.mouth_ding_chance:.0%} chance of a dinged mouth on empty cases; bullet runout with a {cond.runout_sd}° SD tilt.",
        "- Fired cases (`fired` condition): body grows "
        f"{_num(fired.body_growth[0])}–{_num(fired.body_growth[1])} mm and neck {_num(fired.neck_growth[0])}–{_num(fired.neck_growth[1])} mm on diameter "
        "toward the chamber, crimp gone, shoulder up to "
        f"{_num(fired.shoulder_forward[1])} mm forward; firing-pin crater {_num(fired.primer_strike_depth[0])}–{_num(fired.primer_strike_depth[1])} mm deep "
        "(rimfire: crushed rim); extractor nick; dents up to "
        f"{_num(fired.dent_depth[1])} mm deep from rocks and boots; mouths dented "
        f"{_num(fired.mouth_ding_depth[0])}–{_num(fired.mouth_ding_depth[1])} mm ({fired.mouth_ding_chance:.0%} of cases); "
        f"tarnished (age at least {fired.age[0]:g}) and scratched (wear {fired.wear[0]:g}–{fired.wear[1]:g}); soot inside and blow-by outside; dust.",
        "",
        "Sources for the spread: [new brass lot lengths](https://thefiringline.com/forums/showthread.php?p=2300477),",
        "[factory 9mm length variation](https://purple.thefiringline.com/goto/post?id=6804786),",
        "[match .223 length spread](https://www.ssusa.org/articles/2017/8/15/norma-usa-lowers-the-price-bar-for-competition-ammo),",
        "[bulk 55 gr FMJ weight spread](https://www.canadiangunnutz.com/forum/threads/norinco-cj-95-ammunition-powder-and-projectile-measured-weights.1070392/page-3).",
        "",
        *_makers_section(carts),
        "## Sources and notes",
        "",
    ]
    for c in carts:
        out.append(f"### {c.name}")
        out.append("")
        out.append(f"Spec file: [`specs/{c.path.name}`](specs/{c.path.name})")
        out.append("")
        for k, v in c.sources.items():
            out.append(f"- **{k}:** {v}")
        if c.oal_note:
            out.append(f"- **overall length note:** {c.oal_note}")
        out.append("")
    out.append("### Bullets")
    out.append("")
    for b in bl:
        src = "; ".join(f"{k}: {v}" for k, v in b.sources.items())
        out.append(f"- `{b.key}` ([`bullets/{b.path.name}`](bullets/{b.path.name})): {src}")
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
