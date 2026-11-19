# Cartridge specifications

<!-- Generated from specs/*.toml by `python tools/gen_specs_md.py`. Do not edit by hand. -->

All values are millimetres. Case and overall-length values are **maximum cartridge dimensions**
from C.I.P./SAAMI data (see sources below), which is what the models are built to. Real cases
measure slightly under these.

- **≈** estimated or typical value, not from a standard
- **†** derived from the stated shoulder angle
- **—** does not apply

## Cases

| | 9mm Luger | .223 Remington | .45 ACP | .40 S&W | .380 ACP | 7.62×39mm | .308 Winchester | .300 AAC Blackout | .22 Long Rifle |
|---|---|---|---|---|---|---|---|---|---|
| Case length (L3) | 19.15 | 44.7 | 22.81 | 21.59 | 17.27 | 38.7 | 51.18 | 34.75 | 15.57 |
| Base diameter (P1) | 9.93 | 9.58 | 12.09 | 10.77 | 9.5 | 11.35 | 11.96 | 9.6 | 5.74 |
| Neck / mouth diameter (H1) | 9.65 | 6.43 | 12.01 | 10.74 | 9.47 | 8.6 | 8.72 | 8.48 | 5.74 |
| Rim diameter (R1) | 9.96 | 9.6 | 12.19 | 10.77 | 9.5 | 11.35 | 12.01 | 9.6 | 7.06 |
| Rim thickness (R) | 1.27 | 1.14 | 1.24 | 1.4 | 1.14 | 1.5 | 1.37 | 1.14 | 1.09 |
| Shoulder diameter (P2) | — | 9 | — | — | — | 10.07 | 11.53 | 9.16 | — |
| Head to shoulder (L1) | — | 36.52 | — | — | — | ≈30.5 | ≈39.62 | 27.2 | — |
| Head to neck (L2) | — | 39.55 | — | — | — | 33† | 43.48† | 28 | — |
| Shoulder half-angle (°) | — | 23.0† | — | — | — | 16.4 | 20 | 23.0† | — |
| Extractor groove diameter (E1) | ≈8.57 | 8.43 | ≈10.48 | ≈9.26 | ≈8.17 | ≈9.76 | ≈10.33 | 8.43 | — |
| Head to body (E) | ≈3.17 | 3.13 | ≈3.14 | ≈3.3 | ≈3.04 | ≈3.4 | ≈3.27 | 3.15 | — |
| Primer | small-pistol | small-rifle | large-pistol | small-pistol | small-pistol | large-rifle | large-rifle | small-rifle | rimfire |

## Loaded rounds

| | 9mm Luger | .223 Remington | .45 ACP | .40 S&W | .380 ACP | 7.62×39mm | .308 Winchester | .300 AAC Blackout | .22 Long Rifle |
|---|---|---|---|---|---|---|---|---|---|
| Overall length (L6) | 29.69 | 57.4 | 32.39 | 28.83 | 24.99 | 56 | 71.12 | 53.34* | 25.4 |
| Bullet seating depth | 3.96 | 6.10 | 7.72 | 7.76 | 3.58 | 9.50 | 8.56 | 6.01 | 3.30 |

\* see the cartridge's notes below.

## Bullets

Bullets are **typical factory bullets, not standards**: bullet shape varies by load. Diameters follow the standard.

| | 9mm Luger | .223 Remington | .45 ACP | .40 S&W | .380 ACP | 7.62×39mm | .308 Winchester | .300 AAC Blackout | .22 Long Rifle |
|---|---|---|---|---|---|---|---|---|---|
| Bullet | 115 gr FMJ round nose | 55 gr FMJ boat tail | 230 gr FMJ round nose | 180 gr FMJ flat point | 95 gr FMJ round nose | 123 gr FMJ boat tail | 150 gr FMJ boat tail | 125 gr FMJ | 40 gr copper-plated round nose (heeled) |
| Bullet diameter | 9.01 | 5.7 | 11.48 | 10.16 | 9.01 | 7.9 | 7.82 | 7.82 | 5.72 |
| Bullet length | 14.5 | 18.8 | 17.3 | 15 | 11.3 | 26.8 | 28.5 | 24.6 | 13.13 |
| Nose (ogive) length | 7.2 | 11.3 | 9 | 5.6 | 6.2 | 15.8 | 17 | 14.5 | 5.6 |
| Meplat diameter | 2.4 | 0.9 | 3 | 5.6 | 2.2 | 1 | 1 | 1 | 1.8 |
| Boat-tail length | — | 1.5 | — | — | — | 2.5 | 2.6 | — | — |
| Boat-tail half-angle (°) | — | 9 | — | — | — | 10 | 9 | — | — |

## Sources and notes

### 9mm Luger

Spec file: [`specs/9mm.toml`](specs/9mm.toml)

- **case:** Wikipedia 9×19mm Parabellum infobox; drawing captioned 'maximum C.I.P. cartridge dimensions' — https://en.wikipedia.org/wiki/9%C3%9719mm_Parabellum
- **oal:** same as case
- **bullet:** typical 115 gr FMJ RN, not a standard
- **estimated case values:** groove_dia, groove_top

### .223 Remington

Spec file: [`specs/223.toml`](specs/223.toml)

- **case:** C.I.P. TDCC 223 Rem., Tab. I, rev. 17-05-17 (cartridge maxi) — https://bobp.cip-bobp.org/uploads/tdcc/tab-i/223-rem-170406-en.pdf
- **oal:** same as case
- **bullet:** typical 55 gr FMJBT (M193 style), not a standard

### .45 ACP

Spec file: [`specs/45ACP.toml`](specs/45ACP.toml)

- **case:** Wikipedia .45 ACP infobox (inch values converted) — https://en.wikipedia.org/wiki/.45_ACP
- **oal:** same as case
- **bullet:** typical 230 gr FMJ RN, not a standard
- **estimated case values:** groove_dia, groove_top

### .40 S&W

Spec file: [`specs/40CAL.toml`](specs/40CAL.toml)

- **case:** Wikipedia .40 S&W infobox (inch values converted; drawing captioned C.I.P. maximum) — https://en.wikipedia.org/wiki/.40_S%26W
- **oal:** same as case
- **bullet:** typical 180 gr FMJ FP, not a standard
- **estimated case values:** groove_dia, groove_top

### .380 ACP

Spec file: [`specs/380ACP.toml`](specs/380ACP.toml)

- **case:** Wikipedia .380 ACP infobox (inch values converted) — https://en.wikipedia.org/wiki/.380_ACP
- **oal:** same as case
- **bullet:** typical 95 gr FMJ RN, not a standard
- **estimated case values:** groove_dia, groove_top

### 7.62×39mm

Spec file: [`specs/762x39.toml`](specs/762x39.toml)

- **case:** Wikipedia 7.62×39mm infobox (drawing captioned C.I.P. maximum); bullet dia is SAAMI 7.85–7.90, C.I.P. 7.92 — https://en.wikipedia.org/wiki/7.62%C3%9739mm
- **oal:** same as case
- **bullet:** typical 123 gr FMJBT (M43 style), not a standard
- **estimated case values:** groove_dia, groove_top, shoulder_start

### .308 Winchester

Spec file: [`specs/308.toml`](specs/308.toml)

- **case:** Wikipedia .308 Winchester infobox (drawing captioned C.I.P. maximum) — https://en.wikipedia.org/wiki/.308_Winchester
- **oal:** same as case
- **bullet:** typical 150 gr FMJBT (M80 style), not a standard
- **estimated case values:** groove_dia, groove_top, shoulder_start

### .300 AAC Blackout

Spec file: [`specs/300blackout.toml`](specs/300blackout.toml)

- **case:** C.I.P. TDCC 300 AAC Blackout, Tab. I, rev. 18-10-17 (cartridge maxi) — https://bobp.cip-bobp.org/uploads/tdcc/tab-i/300-aac-blackout-180801-en.pdf
- **oal:** typical factory load; see note
- **bullet:** typical 125 gr FMJ, not a standard
- **overall length note:** typical factory length for 110–125 gr loads (2.100 in); the C.I.P. maximum L6 is 57.40, meant for long subsonic bullets

### .22 Long Rifle

Spec file: [`specs/22LR.toml`](specs/22LR.toml)

- **case:** Wikipedia .22 Long Rifle infobox (inch values converted) — https://en.wikipedia.org/wiki/.22_Long_Rifle
- **oal:** same as case
- **bullet:** typical 40 gr plated LRN, not a standard
