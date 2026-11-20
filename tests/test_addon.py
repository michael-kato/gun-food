"""Smoke test for the Blender add-on. Runs inside Blender:

    blender --background --factory-startup --python tests/test_addon.py
    blender --background --python tests/test_addon.py -- --installed   # an installed, enabled extension

Exercises every operator (add, overrides, a bad override, re-roll, duplicate, catalog,
EEVEE tuning) and checks the copies, collections and leftover data. ~40 s, most of it the catalog.
"""

import sys
from pathlib import Path

import bpy

ARGS = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
INSTALLED = "--installed" in ARGS
FAILS = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


if INSTALLED:
    pkg = next((m for name, m in sys.modules.items() if name.endswith(".gun_food") and name.startswith("bl_ext.")), None)
    check(pkg is not None, "extension is installed and enabled")
    if pkg is None:
        sys.exit(1)
    specs = sys.modules[pkg.__name__ + ".specs"]
    check(Path(specs.SPEC_DIR).parent.name == "data", f"specs load from the bundled data ({specs.SPEC_DIR})")
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import cartridges
    from cartridges import specs

    cartridges.register()

scene = bpy.context.scene
s = scene.gun_food
ops = bpy.ops.gunfood


def roots():
    return [o for o in bpy.data.objects if o.get("cartridge") and o.parent is None]


# add: default cartridge, overrides never touched (they must not leak into the spec)
s.use_overrides = False
s.random_seed = False
s.seed = 7
s.cartridge = "9mm"
check(ops.add_cartridges() == {"FINISHED"}, "add 7 loaded 9mm")
check(len(roots()) == 7, f"7 copies (got {len(roots())})")
check(len({r["seed"] for r in roots()}) == 7, "every copy has its own seed")
coll = bpy.data.collections.get("Gun Food 9mm")
check(coll is not None and len(coll.objects) == 7 * 4, "copies land in 'Gun Food 9mm' (root, case, primer, bullet each)")
primers = {o.data.name for o in bpy.data.objects if o.name.endswith(".primer")}
check(len(primers) == 1, f"one shared primer mesh per add (got {len(primers)})")

# fired and empty cases, a row
s.cartridge, s.kind, s.count, s.arrangement = "308", "fired", 5, "ROW"
check(ops.add_cartridges() == {"FINISHED"}, "add 5 fired 308 in a row")
fired = [r for r in roots() if r["cartridge"] == "308"]
check(len(fired) == 5 and all(r["kind"] == "fired" and r["soot_in"] > 0 for r in fired), "fired copies carry soot")
s.cartridge, s.kind, s.count, s.arrangement = "22LR", "case", 3, "HEX"
check(ops.add_cartridges() == {"FINISHED"}, "add 3 empty 22LR cases")

# overrides: ticking the box loads the spec; a longer case gives longer copies
s.cartridge, s.kind, s.count = "45ACP", "loaded", 7
s.ov_key = ""
s.use_overrides = True
base = specs.load_all()
spec45 = next(c for c in base if c.key == "45ACP")
check(abs(s.ov_length - spec45.case.length) < 1e-4, "enabling overrides loads the spec values")
s.ov_length = spec45.case.length + 2.0
s.ov_oal = spec45.nominal_oal + 2.0
check(ops.add_cartridges() == {"FINISHED"}, "add with a 2 mm longer case")
long45 = [r for r in roots() if r["cartridge"] == "45ACP"]
check(all(r["case_length"] > spec45.case.length + 1.0 for r in long45), "override reaches the copies")
check(all(r["oal"] > spec45.oal_max for r in long45), "loaded length follows the override past SAAMI's max")

# a bad override is refused, nothing is added
s.cartridge = "223"
s.use_overrides = False
s.use_overrides = True
n = len(roots())
s.ov_mouth_dia = 12.0  # wider than the shoulder
try:  # an operator's error report raises when it's called from a script
    refused = ops.add_cartridges() == {"CANCELLED"}
except RuntimeError as e:
    refused = "not buildable" in str(e)
check(refused, "unbuildable override is refused")
check(len(roots()) == n, "and adds nothing")
s.use_overrides = False

# re-roll keeps placement and collections, swaps the seeds, leaves no orphan meshes
for o in bpy.context.selected_objects:
    o.select_set(False)
sel = [r for r in roots() if r["cartridge"] == "9mm"]
for r in sel:
    r.select_set(True)
before = {round(r.location.x, 6): r["seed"] for r in sel}
meshes = len(bpy.data.meshes)
s.random_seed = True
check(ops.reroll() == {"FINISHED"}, "re-roll the 9mm copies")
after = {round(r.location.x, 6): r["seed"] for r in roots() if r["cartridge"] == "9mm"}
check(sorted(before) == sorted(after), "same positions")
check(all(before[x] != after[x] for x in before), "new seeds")
check(len(coll.objects) == 7 * 4, "still in their collection")
check(len(bpy.data.meshes) <= meshes, f"no orphan meshes ({meshes} -> {len(bpy.data.meshes)})")

# duplicate as a new variation
n = len(roots())
check(ops.duplicate_variation() == {"FINISHED"}, "duplicate the selection")
check(len(roots()) == n + 7, "7 new copies")

# catalog and EEVEE
n = len(roots())
check(ops.build_catalog() == {"FINISHED"}, "add the catalog")
check(len(roots()) - n == len(base) * 21, f"catalog adds {len(base) * 21} copies (got {len(roots()) - n})")
check(ops.tune_eevee() == {"FINISHED"}, "tune EEVEE")
rto = getattr(scene.eevee, "ray_tracing_options", None)
check(rto is None or abs(rto.screen_trace_thickness - 0.002) < 1e-6, "trace thickness 2 mm")

# panels: draw into a stand-in layout that checks every property, operator and icon name
ICONS = set(bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys())
bad = []


class Layout:
    enabled = True

    def __getattr__(self, name):  # column, row, box, separator, ...
        return lambda *a, **k: self

    def prop(self, data, name, **k):
        if name not in data.bl_rna.properties:
            bad.append(f"property {name}")
        self._icon(k)

    def operator(self, idname, **k):
        mod, op = idname.split(".")
        if not hasattr(getattr(bpy.ops, mod), op):
            bad.append(f"operator {idname}")
        self._icon(k)

    def label(self, **k):
        self._icon(k)

    def _icon(self, k):
        if k.get("icon") and k["icon"] not in ICONS:
            bad.append(f"icon {k['icon']}")


panels = [c for c in bpy.types.Panel.__subclasses__() if c.__name__.startswith("GUNFOOD_PT")]
for use in (False, True):
    s.use_overrides = use
    for p in panels:
        stub = type("P", (), {"layout": Layout()})()
        for fn in ("draw_header", "draw"):
            if hasattr(p, fn):
                getattr(p, fn)(stub, bpy.context)
check(len(panels) == 2 and not bad, f"panels draw ({len(panels)} panels; bad names: {bad or 'none'})")

if not INSTALLED:
    cartridges.unregister()
    check(not hasattr(bpy.types.Scene, "gun_food"), "unregister cleans up")

print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
