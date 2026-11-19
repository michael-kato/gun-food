# cartridges

Parametric, dimensionally accurate 3D models of firearm cartridges for Blender, with
procedural, physically based materials. Every case, primer and bullet is generated from a
small TOML spec, so adding a cartridge or changing a dimension means editing numbers, not
remodelling.

Built for synthetic training data (casing / caliber recognition) and for artists who want
correct proportions.

![Overview](docs/img/overview.jpg)

![Side lineup](docs/img/lineup.jpg)

![Headstamps](docs/img/headstamps.jpg)

## What's included

| Key | Cartridge | Case dimensions from |
|---|---|---|
| `9mm` | 9mm Luger (9×19mm) | Wikipedia infobox (C.I.P. maximum) |
| `223` | .223 Remington | C.I.P. data sheet |
| `45ACP` | .45 ACP | Wikipedia infobox |
| `40CAL` | .40 S&W | Wikipedia infobox (C.I.P. maximum) |
| `380ACP` | .380 ACP | Wikipedia infobox |
| `762x39` | 7.62×39mm | Wikipedia infobox (C.I.P. maximum); head-to-shoulder estimated |
| `308` | .308 Winchester | Wikipedia infobox (C.I.P. maximum); head-to-shoulder estimated |
| `300blackout` | .300 AAC Blackout | C.I.P. data sheet |
| `22LR` | .22 Long Rifle | Wikipedia infobox |

**[SPECS.md](SPECS.md)** lists every dimension, which ones are estimated, and the source of each.
It's generated from the spec files, so it always matches the models.

`cartridges.blend` holds every cartridge in three tightly packed groups of seven (loaded
rounds, primed empty cases, bullets), with 10 mm between groups. All copies of a part share
one mesh, so the file stays small, but each copy gets its own surface imperfections.

## Build

Needs Blender 4.2 or newer (developed on 5.2). No other dependencies.

```sh
blender --background --factory-startup --python build.py -- --report docs/dimension_check.md
```

| Option | Does |
|---|---|
| `--out PATH` | where to write the .blend (default `cartridges.blend`) |
| `--only 9mm 308` | build only some cartridges |
| `--render DIR` | also render overview, side lineup and headstamp images |
| `--report PATH` | write a table of measured mesh dimensions vs. spec ([example](docs/dimension_check.md)) |
| `--cpu` | render on the CPU |

The build takes about a second. Rendering the three preview images takes about 20 s on a
mid-range GPU.

## How it works

```
specs/*.toml ──▶ specs.py      load, fill defaults, validate (pure Python)
             ──▶ profiles.py   2D half-profiles: case, primer, bullet (pure Python)
             ──▶ blender/mesh.py       revolve profiles into watertight meshes, cut headstamps
             ──▶ blender/materials.py  procedural metals
             ──▶ blender/scene.py      groups, studio, cameras, dimension check, renders
```

- **Cases** are revolved from a closed profile: rim with chamfer, extractor groove (rim bevel,
  flat, ramp), tapered body, shoulder and neck with fillets, mouth chamfers, inner wall
  thickening toward the web, primer pocket and flash hole. Rimfire cases get a folded,
  hollow rim instead.
- **Bullets** use a tangent ogive computed from nose length and meplat, plus optional boat
  tail, cannelure, exposed lead base (open-base FMJ) and heel (.22 LR).
- **Headstamps** are real geometry: text is laid out on arcs around the primer and stamped
  0.12 mm into the head with a boolean (raised for rimfire).
- **Materials** are one shared node graph with per-metal parameters: measured reflectance
  as base colour, an F82 edge tint, faint tarnish with a thin oxide film, drawing marks
  along the axis, sparse dings, and residue in recesses. Rifle necks show an annealing
  stain, set per object with the custom properties `anneal_z0`, `anneal_z1` (mm from the
  head) and `anneal_amt` (0–1). Metals available: brass, gilding metal, copper, lead,
  nickel, steel, aluminium.

## Adding or changing a cartridge

1. Copy a similar file in `specs/` (straight-walled pistol: `9mm.toml`; bottleneck rifle:
   `223.toml`; rimfire: `22LR.toml`) and edit the numbers. Field names follow C.I.P.
   drawings; `cartridges/specs.py` documents every field and its default.
2. For a bottleneck case, give `shoulder_start` (L1) and either `neck_start` (L2) or
   `shoulder_angle`.
3. List anything you estimated in `approx = [...]` and fill in `[sources]`.
4. Run the checks and regenerate the docs:

   ```sh
   python tests/test_specs_and_profiles.py
   python tools/gen_specs_md.py
   ```

The loader rejects specs that can't be built (for example a bullet seated past the case
web, or a neck wider than the shoulder) with a message saying what to fix.

## Accuracy

- Case and overall-length numbers are **maximum cartridge** dimensions from published
  C.I.P./SAAMI data. Values not found in a source are marked ≈ in SPECS.md.
- Bullet shapes, wall thickness, primer seating and extractor grooves (where no C.I.P.
  sheet was used) are typical values for realistic looks.
- `build.py --report` measures the generated meshes against the specs. The current build
  matches to 0.000 mm.
- C.I.P. data sheets are cited by link, not reproduced.
- These are visual models. Don't use them as reloading or chamber data.

## Headstamps

Maker marks are the placeholder `CMX` (and `M` on rimfire). The caliber text follows real
practice (`223 REM`, `45 AUTO`, …). Change `[headstamp]` in a spec to use your own.

## Roadmap

- Case variations: steel (lacquered and polymer coated), aluminium, nickel plated
- More bullet types: hollow point, soft point, polymer tip, lead round nose, wadcutter
- Fired and damaged cases: firing pin strike, extractor marks, flattened, split necks, dents
- More cartridges, and a Blender add-on panel to build them without the command line

## License

MIT, see [LICENSE](LICENSE).
