# Cartridge specifications

<!-- Generated from specs/*.toml and bullets/*.toml by `python tools/gen_specs_md.py`. Do not edit by hand. -->

All values are millimetres. Case values are **SAAMI maximum cartridge dimensions** with
SAAMI's minus tolerance: `19.15 −0.25` means a real case measures between 18.90 and 19.15.

- **≈** estimated or typical value, not from a standard
- **†** derived from the stated shoulder angle
- **—** does not apply

## Cases

| | 9mm Luger | .223 Remington | .45 ACP | .40 S&W | .380 ACP | 7.62×39mm | .308 Winchester | .300 AAC Blackout | .22 Long Rifle |
|---|---|---|---|---|---|---|---|---|---|
| Case length (L3) | 19.15 −0.25 | 44.7 −0.76 | 22.81 −0.25 | 21.59 −0.25 | 17.27 −0.25 | 38.81 −0.38 | 51.18 −0.51 | 34.75 −0.51 | 15.57 −0.2 |
| Base diameter (P1) | 9.931 −0.18 | 9.548 −0.2 | 12.09 −0.15 | 10.77 −0.2 | 9.497 −0.15 | 11.252 −0.2 | 11.946 −0.2 | 9.548 −0.13 | 5.74 −0.1 |
| Shoulder diameter (P2) | — | 8.997 −0.2 | — | — | — | 10.058 −0.2 | 11.532 −0.2 | 9.162 −0.13 | — |
| Neck / mouth diameter (H1) | 9.653 −0.18 | 6.43 −0.2 | 12.014 −0.15 | 10.74 −0.2 | ≈9.474 −0.15 | 8.61 −0.2 | 8.725 −0.2 | 8.48 −0.13 | 5.74 −0.1 |
| Head to shoulder (L1) | — | 36.527 −0.178 | — | — | — | 30.441 −0.178 | 39.62 −0.178 | 27.195 −0.178 | — |
| Head to neck (L2) | — | 39.555 −0.178 | — | — | — | 32.735 −0.178 | 43.475 −0.178 | 27.992 −0.178 | — |
| Rim diameter (R1) | 10.01 −0.25 | 9.6 −0.25 | 12.19 −0.25 | 10.77 −0.25 | 9.5 −0.25 | 11.35 −0.25 | 12.01 −0.25 | 9.6 −0.25 | 7.06 −0.3 |
| Rim thickness (R) | 1.27 −0.25 | 1.14 −0.25 | 1.24 −0.25 | 1.4 −0.25 | 1.14 −0.25 | 1.45 −0.25 | 1.37 −0.25 | 1.14 −0.25 | 1.09 −0.18 |
| Extractor groove diameter (E1) | ≈8.81 −0.51 | 8.43 −0.51 | 10.16 −0.25 | ≈8.81 −0.51 | ≈8.36 −0.25 | 9.55 −0.25 | 10.39 −0.51 | 8.43 −0.51 | — |
| Head to body (E) | ≈3.17 | 3.13 | ≈3.14 | ≈3.3 | ≈3.04 | ≈3.35 | ≈3.27 | 3.15 | — |
| Primer | small-pistol | small-rifle | large-pistol | small-pistol | small-pistol | large-rifle | large-rifle | small-rifle | rimfire |

## Loaded rounds

| | 9mm Luger | .223 Remington | .45 ACP | .40 S&W | .380 ACP | 7.62×39mm | .308 Winchester | .300 AAC Blackout | .22 Long Rifle |
|---|---|---|---|---|---|---|---|---|---|
| Bullet | [`355-115-fmj-rn`](#355-115-fmj-rn) | [`224-55-fmjbt`](#224-55-fmjbt) | [`452-230-fmj-rn`](#452-230-fmj-rn) | [`400-180-fmj-fp`](#400-180-fmj-fp) | [`355-95-fmj-rn`](#355-95-fmj-rn) | [`311-123-fmjbt`](#311-123-fmjbt) | [`308-150-fmjbt`](#308-150-fmjbt) | [`308-125-fmj`](#308-125-fmj) | [`224-40-lrn-plated`](#224-40-lrn-plated) |
| Overall length, SAAMI min–max | 25.4–29.69 | 53.98–57.4 | 30.23–32.39 | 27.56–28.83 | 23.11–24.99 | 54.61–55.88 | 63.25–71.37 | 45.21–57.4 | 24.13–25.4 |
| Overall length, as built | 29.21 | 56.90 (cannelure) | 32.00 | 28.58 | 24.89 | 55.60 (cannelure) | 70.60 (cannelure) | 53.00 (cannelure) | 25.02 |
| Seating depth | 4.44 | 6.60 | 8.11 | 8.01 | 3.68 | 10.01 | 9.08 | 6.35 | 3.30 |
| Crimp | taper, ≈0.06 on dia | roll, ≈0.15 on dia | taper, ≈0.06 on dia | taper, ≈0.06 on dia | taper, ≈0.06 on dia | roll, ≈0.15 on dia | roll, ≈0.15 on dia | roll, ≈0.15 on dia | roll, ≈0.1 on dia |
| Maximum bullet diameter | 9.03 | 5.702 | 11.481 | 10.173 | 9.055 | 7.9 | 7.85 | 7.85 | 5.728 |

Roll-crimped rounds seat with the case mouth in the bullet's cannelure, so their length follows the
bullet. Taper-crimped pistol rounds use a typical factory length. Crimp amounts are typical values
from reloading references, not standards.

## Bullets

Bullets live in `bullets/` and are shared: any cartridge can load any bullet that fits. Diameters
are SAAMI maximums with SAAMI's tolerance; **shapes are typical factory bullets, not standards**.

| | <a id="224-40-lrn-plated"></a>`224-40-lrn-plated` | <a id="224-55-fmjbt"></a>`224-55-fmjbt` | <a id="308-125-fmj"></a>`308-125-fmj` | <a id="308-150-fmjbt"></a>`308-150-fmjbt` | <a id="311-123-fmjbt"></a>`311-123-fmjbt` | <a id="355-115-fmj-rn"></a>`355-115-fmj-rn` | <a id="355-95-fmj-rn"></a>`355-95-fmj-rn` | <a id="400-180-fmj-fp"></a>`400-180-fmj-fp` | <a id="452-230-fmj-rn"></a>`452-230-fmj-rn` |
|---|---|---|---|---|---|---|---|---|---|
| Bullet | .22 40 gr copper-plated round nose (heeled) | .224 55 gr FMJ boat tail | .308 125 gr FMJ | .308 150 gr FMJ boat tail | .311 123 gr FMJ boat tail | 9mm 115 gr FMJ round nose | 9mm 95 gr FMJ round nose | .40 180 gr FMJ flat point | .45 230 gr FMJ round nose |
| Used by | .22 Long Rifle | .223 Remington | .300 AAC Blackout | .308 Winchester | 7.62×39mm | 9mm Luger | .380 ACP | .40 S&W | .45 ACP |
| Tip | round | round | round | round | round | round | round | flat | round |
| Diameter (max) | 5.728 −0.102 | 5.702 −0.076 | 7.85 −0.08 | 7.85 −0.08 | 7.9 −0.05 | 9.03 −0.076 | 9.03 −0.076 | 10.173 −0.076 | 11.481 −0.076 |
| Length | 12.75 ±0.102 | 18.8 ±0.15 | 24.6 ±0.196 | 28.5 ±0.228 | 26.8 ±0.214 | 14.5 ±0.116 | 11.3 ±0.09 | 15 ±0.12 | 17.3 ±0.138 |
| Nose (ogive) length | 5.6 | 11.3 | 14.5 | 17 | 15.8 | 7.4 | 6.3 | 5.6 | 9.2 |
| Tip diameter | 2.4 | 0.9 | 1 | 1 | 1 | 3.2 | 3 | 5.6 | 4 |
| Boat-tail length | — | 1.5 | — | 2.6 | 2.5 | — | — | — | — |
| Boat-tail half-angle (°) | — | 9 | — | 9 | 10 | — | — | — | — |
| Cannelure, from base | — | 6.25 | 6 | 8.73 | 9.66 | — | — | — | — |
| Heel length | 3.3 | — | — | — | — | — | — | — | — |

## Variation between copies

Every copy in the scene is a separate, seeded sample of its spec (`cartridges/variation.py`):

- Dimensions are drawn inside the SAAMI band. Real parts don't fill the band evenly, so samples
  cluster at these fractions of the band below max (mean, standard deviation), inferred from
  reloading-forum lot measurements:

  | Group | Mean | SD |
  |---|---|---|
  | length | 0.25 | 0.10 |
  | diameter | 0.35 | 0.12 |
  | rim | 0.30 | 0.12 |
  | headspace | 0.40 | 0.12 |
  | bullet_dia | 0.30 | 0.12 |

- Loaded length varies with a 0.08 mm (pistol) / 0.06 mm (rifle) standard deviation, clamped to
  SAAMI's limits. Bullet length varies 0.4% (one SD).
- Factory-new handling damage: about 0.6 dents per 10 mm of case, 0.008–0.05 mm deep; up to 0.015 mm out-of-round at the mouth;
  a 25% chance of a dinged mouth on empty cases; bullet runout with a 0.12° SD tilt.
- Fired cases (`fired` condition): body grows 0.03–0.1 mm and neck 0.05–0.15 mm on diameter toward the chamber, crimp gone, shoulder up to 0.08 mm forward; firing-pin crater 0.2–0.5 mm deep (rimfire: crushed rim); extractor nick; dents up to 0.2 mm deep from rocks and boots; soot inside and blow-by outside; dirt.

Sources for the spread: [new brass lot lengths](https://thefiringline.com/forums/showthread.php?p=2300477),
[factory 9mm length variation](https://purple.thefiringline.com/goto/post?id=6804786),
[match .223 length spread](https://www.ssusa.org/articles/2017/8/15/norma-usa-lowers-the-price-bar-for-competition-ammo),
[bulk 55 gr FMJ weight spread](https://www.canadiangunnutz.com/forum/threads/norinco-cj-95-ammunition-powder-and-projectile-measured-weights.1070392/page-3).

## Sources and notes

### 9mm Luger

Spec file: [`specs/9mm.toml`](specs/9mm.toml)

- **case:** ANSI/SAAMI Z299.3-2022, 9mm Luger cartridge drawing (rev. 06/23/2021) — https://saami.org/wp-content/uploads/2025/05/SAAMI-Z299.3-2022-Centerfire-Pistol-Revolver-Approved-12-13-2022.pdf
- **groove:** read from the drawing text; its position on the drawing was not checked
- **crimp:** taper crimp to about bullet + 2 walls - .004 in; factory .45 measures .469-.472 in — https://www.handgunsmag.com/editorial/squeeze-play-how-to-properly-crimp-ammunition/138116, https://snipershide.com/shooting/threads/45-acp-taper-crimp-spec.6893857

### .223 Remington

Spec file: [`specs/223.toml`](specs/223.toml)

- **case:** ANSI/SAAMI Z299.4-2025, 223 Remington cartridge drawing (rev. 09/25/2023) — https://saami.org/wp-content/uploads/2026/10/SAAMI-Z299.4-CFR-2025-Centerfire-Rifle-Approved-2-10-2025-2026-10-21.pdf
- **groove_top:** C.I.P. TDCC 223 Rem. — https://bobp.cip-bobp.org/uploads/tdcc/tab-i/223-rem-170406-en.pdf

### .45 ACP

Spec file: [`specs/45ACP.toml`](specs/45ACP.toml)

- **case:** ANSI/SAAMI Z299.3-2022, 45 Automatic cartridge drawing (rev. 10/13/1992) — https://saami.org/wp-content/uploads/2025/05/SAAMI-Z299.3-2022-Centerfire-Pistol-Revolver-Approved-12-13-2022.pdf
- **crimp:** factory .45 Auto mouths measure .469-.472 in after crimp — https://snipershide.com/shooting/threads/45-acp-taper-crimp-spec.6893857

### .40 S&W

Spec file: [`specs/40CAL.toml`](specs/40CAL.toml)

- **case:** ANSI/SAAMI Z299.3-2022, 40 S&W cartridge drawing (rev. 07/09/2021) — https://saami.org/wp-content/uploads/2025/05/SAAMI-Z299.3-2022-Centerfire-Pistol-Revolver-Approved-12-13-2022.pdf
- **groove:** read from the drawing text; its position on the drawing was not checked
- **crimp:** taper crimp to about bullet + 2 walls - .004 in — https://www.handgunsmag.com/editorial/squeeze-play-how-to-properly-crimp-ammunition/138116

### .380 ACP

Spec file: [`specs/380ACP.toml`](specs/380ACP.toml)

- **case:** ANSI/SAAMI Z299.3-2022, 380 Automatic cartridge drawing (rev. 07/09/2021) — https://saami.org/wp-content/uploads/2025/05/SAAMI-Z299.3-2022-Centerfire-Pistol-Revolver-Approved-12-13-2022.pdf
- **groove:** groove and mouth diameters read from the drawing text; positions not checked
- **crimp:** taper crimp to about bullet + 2 walls - .004 in — https://www.handgunsmag.com/editorial/squeeze-play-how-to-properly-crimp-ammunition/138116

### 7.62×39mm

Spec file: [`specs/762x39.toml`](specs/762x39.toml)

- **case:** ANSI/SAAMI Z299.4-2025, 7.62x39 cartridge drawing (rev. 02/28/2022) — https://saami.org/wp-content/uploads/2026/10/SAAMI-Z299.4-CFR-2025-Centerfire-Rifle-Approved-2-10-2025-2026-10-21.pdf

### .308 Winchester

Spec file: [`specs/308.toml`](specs/308.toml)

- **case:** ANSI/SAAMI Z299.4-2025, 308 Winchester cartridge drawing (rev. 06/03/2022) — https://saami.org/wp-content/uploads/2026/10/SAAMI-Z299.4-CFR-2025-Centerfire-Rifle-Approved-2-10-2025-2026-10-21.pdf

### .300 AAC Blackout

Spec file: [`specs/300blackout.toml`](specs/300blackout.toml)

- **case:** ANSI/SAAMI Z299.4-2025, 300 AAC Blackout cartridge drawing (rev. 05/20/2022) — https://saami.org/wp-content/uploads/2026/10/SAAMI-Z299.4-CFR-2025-Centerfire-Rifle-Approved-2-10-2025-2026-10-21.pdf
- **groove_top:** C.I.P. TDCC 300 AAC Blackout — https://bobp.cip-bobp.org/uploads/tdcc/tab-i/300-aac-blackout-180801-en.pdf

### .22 Long Rifle

Spec file: [`specs/22LR.toml`](specs/22LR.toml)

- **case:** ANSI/SAAMI Z299.1-2026, 22 Long Rifle - Sporting cartridge drawing (rev. 01/19/2025) — https://saami.org/wp-content/uploads/2026/05/SAAMI-Z299.1-R2026-Rimfire-FINAL-Approved-2026-05-08.pdf

### Bullets

- `224-40-lrn-plated` ([`bullets/224-40-lrn-plated.toml`](bullets/224-40-lrn-plated.toml)): dia: ANSI/SAAMI Z299.1-2026, 22 Long Rifle - Sporting cartridge drawing — https://saami.org/wp-content/uploads/2026/05/SAAMI-Z299.1-R2026-Rimfire-FINAL-Approved-2026-05-08.pdf; shape: typical 40 gr plated LRN, not a standard
- `224-55-fmjbt` ([`bullets/224-55-fmjbt.toml`](bullets/224-55-fmjbt.toml)): dia: ANSI/SAAMI Z299.4-2025, 223 Remington cartridge drawing — https://saami.org/wp-content/uploads/2026/10/SAAMI-Z299.4-CFR-2025-Centerfire-Rifle-Approved-2-10-2025-2026-10-21.pdf; shape: typical 55 gr FMJBT (M193 style), not a standard
- `308-125-fmj` ([`bullets/308-125-fmj.toml`](bullets/308-125-fmj.toml)): dia: ANSI/SAAMI Z299.4-2025, 300 AAC Blackout cartridge drawing — https://saami.org/wp-content/uploads/2026/10/SAAMI-Z299.4-CFR-2025-Centerfire-Rifle-Approved-2-10-2025-2026-10-21.pdf; shape: typical 125 gr FMJ, not a standard
- `308-150-fmjbt` ([`bullets/308-150-fmjbt.toml`](bullets/308-150-fmjbt.toml)): dia: ANSI/SAAMI Z299.4-2025, 308 Winchester cartridge drawing — https://saami.org/wp-content/uploads/2026/10/SAAMI-Z299.4-CFR-2025-Centerfire-Rifle-Approved-2-10-2025-2026-10-21.pdf; shape: typical 150 gr FMJBT (M80 style), not a standard
- `311-123-fmjbt` ([`bullets/311-123-fmjbt.toml`](bullets/311-123-fmjbt.toml)): dia: ANSI/SAAMI Z299.4-2025, 7.62x39 cartridge drawing — https://saami.org/wp-content/uploads/2026/10/SAAMI-Z299.4-CFR-2025-Centerfire-Rifle-Approved-2-10-2025-2026-10-21.pdf; shape: typical 123 gr FMJBT (M43 style), not a standard
- `355-115-fmj-rn` ([`bullets/355-115-fmj-rn.toml`](bullets/355-115-fmj-rn.toml)): dia: ANSI/SAAMI Z299.3-2022, 9mm Luger cartridge drawing — https://saami.org/wp-content/uploads/2025/05/SAAMI-Z299.3-2022-Centerfire-Pistol-Revolver-Approved-12-13-2022.pdf; shape: typical 115 gr FMJ RN, not a standard
- `355-95-fmj-rn` ([`bullets/355-95-fmj-rn.toml`](bullets/355-95-fmj-rn.toml)): dia: ANSI/SAAMI Z299.3-2022 — https://saami.org/wp-content/uploads/2025/05/SAAMI-Z299.3-2022-Centerfire-Pistol-Revolver-Approved-12-13-2022.pdf; shape: typical 95 gr FMJ RN, not a standard
- `400-180-fmj-fp` ([`bullets/400-180-fmj-fp.toml`](bullets/400-180-fmj-fp.toml)): dia: ANSI/SAAMI Z299.3-2022, 40 S&W cartridge drawing — https://saami.org/wp-content/uploads/2025/05/SAAMI-Z299.3-2022-Centerfire-Pistol-Revolver-Approved-12-13-2022.pdf; shape: typical 180 gr FMJ FP, not a standard
- `452-230-fmj-rn` ([`bullets/452-230-fmj-rn.toml`](bullets/452-230-fmj-rn.toml)): dia: ANSI/SAAMI Z299.3-2022, 45 Auto cartridge drawing — https://saami.org/wp-content/uploads/2025/05/SAAMI-Z299.3-2022-Centerfire-Pistol-Revolver-Approved-12-13-2022.pdf; shape: typical 230 gr FMJ RN, not a standard
