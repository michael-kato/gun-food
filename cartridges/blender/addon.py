"""Blender add-on: a "Gun Food" tab in the 3D Viewport sidebar (N).

* **Add**: place N seeded copies of a cartridge at the 3D cursor (loaded rounds, new
  primed cases or fired cases), packed in a hex cluster or a row.
* **Re-roll**: rebuild the selected copies with new seeds, in place.
* **Duplicate as New Variation**: copies of the selection, each a new sample.
* **Overrides**: change the spec's maximum dimensions before sampling; the copies still
  vary inside the cartridge's tolerances around the new values.
* **Catalog**: the full grouped layout of every cartridge, as ``build.py`` makes it.

All geometry and materials come from the same code as ``build.py``; the specs are the
TOML files bundled with the extension.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from mathutils import Matrix, Vector

from .. import specs, variation
from . import scene as sc
from .mesh import MM

ROOT_COLLECTION = "Gun Food"
KINDS = [
    ("loaded", "Loaded Round", "Case, primer and crimped bullet, factory new"),
    ("case", "New Case", "Primed empty case, factory new"),
    ("fired", "Fired Case", "Expanded, struck, sooty and dirty, as found on the ground"),
]
OVERRIDES = [
    # (property, label, getter from a Cartridge)
    ("ov_length", "Case Length", lambda c: c.case.length),
    ("ov_base_dia", "Base Diameter", lambda c: c.case.base_dia),
    ("ov_mouth_dia", "Mouth Diameter", lambda c: c.case.mouth_dia),
    ("ov_rim_dia", "Rim Diameter", lambda c: c.case.rim_dia),
    ("ov_rim_thickness", "Rim Thickness", lambda c: c.case.rim_thickness),
    ("ov_oal", "Overall Length", lambda c: c.nominal_oal),
    ("ov_crimp", "Crimp", lambda c: c.crimp_amount),
]

_carts: dict | None = None
_items: list = []  # Blender needs dynamic enum items kept alive


def carts() -> dict:
    global _carts
    if _carts is None:
        _carts = {c.key: c for c in specs.load_all()}
    return _carts


def _cart_items(self, context):
    global _items
    _items = [(c.key, c.name, f"{c.name}, {c.bullet.name}") for c in carts().values()]
    return _items


def _fill_overrides(self, context=None):
    c = carts().get(self.cartridge)
    if c:
        for prop, _, get in OVERRIDES:
            setattr(self, prop, get(c))
        self.ov_key = c.key


def _on_toggle_overrides(self, context):
    if self.use_overrides and self.ov_key != self.cartridge:
        _fill_overrides(self, context)


class GunFoodSettings(bpy.types.PropertyGroup):
    cartridge: EnumProperty(name="Cartridge", items=_cart_items, update=_fill_overrides)
    kind: EnumProperty(name="Kind", items=KINDS, default="loaded")
    count: IntProperty(name="Count", default=7, min=1, max=500)
    arrangement: EnumProperty(
        name="Arrangement",
        items=[("HEX", "Hex Cluster", "Tightly packed, standing"), ("ROW", "Row", "In a line along X, 1 mm apart")],
        default="HEX",
    )
    random_seed: BoolProperty(name="Random Seed", default=True, description="A new seed every time; off to use the seed below")
    seed: IntProperty(name="Seed", default=1, min=0)
    dirt_scale: FloatProperty(name="Dirt", default=1.0, min=0.0, max=3.0, description="Multiplies the condition's dirt")
    soot_scale: FloatProperty(name="Soot", default=1.0, min=0.0, max=3.0, description="Multiplies a fired case's soot")
    use_overrides: BoolProperty(name="Override Spec", default=False, update=_on_toggle_overrides, description="Use the dimensions below instead of the spec's maximums")
    ov_key: StringProperty(options={"HIDDEN"})  # cartridge the override fields were filled from
    ov_length: FloatProperty(name="Case Length (mm)", default=1.0, min=1.0, precision=3)
    ov_base_dia: FloatProperty(name="Base Diameter (mm)", default=1.0, min=1.0, precision=3)
    ov_mouth_dia: FloatProperty(name="Mouth Diameter (mm)", default=1.0, min=1.0, precision=3)
    ov_rim_dia: FloatProperty(name="Rim Diameter (mm)", default=1.0, min=1.0, precision=3)
    ov_rim_thickness: FloatProperty(name="Rim Thickness (mm)", default=1.0, min=0.1, precision=3)
    ov_oal: FloatProperty(name="Overall Length (mm)", default=1.0, min=1.0, precision=3)
    ov_crimp: FloatProperty(name="Crimp (mm on dia)", default=0.0, min=0.0, max=0.5, precision=3)


def effective_cartridge(s: GunFoodSettings, key: str | None = None):
    """The cartridge spec to sample from, with the panel's overrides applied when on.

    Raises ``specs.SpecError`` when the overrides can't be built.
    """
    key = key or s.cartridge
    base = carts()[key]
    if not s.use_overrides or key != s.cartridge:
        return base
    if s.ov_key != key:  # never filled for this cartridge: start from the spec
        _fill_overrides(s)
    case = replace(base.case, length=s.ov_length, base_dia=s.ov_base_dia, mouth_dia=s.ov_mouth_dia, rim_dia=s.ov_rim_dia, rim_thickness=s.ov_rim_thickness)
    c = replace(base, case=case, crimp_amount=s.ov_crimp, approx=set(base.approx))
    if base.oal is not None and not base.seats_on_cannelure:
        c.oal = s.ov_oal
    # move SAAMI's loaded-length limits with the new length, or the copies get clamped back
    shift = c.nominal_oal - base.nominal_oal
    c.oal_min, c.oal_max = base.oal_min + shift, base.oal_max + shift
    return specs.finalize(c)


def _carts_for(op, s, keys):
    """Effective specs for ``keys``, or None (with an error reported) if an override can't be built."""
    try:
        return {k: effective_cartridge(s, k) for k in keys}
    except specs.SpecError as e:
        op.report({"ERROR"}, f"Override not buildable: {e}")
        return None


def _collection(context, key):
    scene_coll = context.scene.collection
    root = bpy.data.collections.get(ROOT_COLLECTION)
    if root is None:
        root = bpy.data.collections.new(ROOT_COLLECTION)
    if root.name not in scene_coll.children:
        scene_coll.children.link(root)
    sub = next((c for c in root.children if c.get("gf_cartridge") == key), None)
    if sub is None:
        sub = bpy.data.collections.new(f"{ROOT_COLLECTION} {key}")
        sub["gf_cartridge"] = key
        root.children.link(sub)
    return sub


def _offsets(n, pitch, arrangement):
    if arrangement == "ROW":
        return [(i * pitch, 0.0) for i in range(n)]
    pts = []
    ring = 0
    while len(pts) < n:  # hex spiral: centre, then rings of 6, 12, ...
        if ring == 0:
            pts.append((0.0, 0.0))
        else:
            q, r = ring, 0
            for side in range(6):
                for _ in range(ring):
                    pts.append((pitch * (q + r / 2), pitch * r * math.sqrt(3) / 2))
                    dq, dr = [(-1, 1), (-1, 0), (0, -1), (1, -1), (1, 0), (0, 1)][side]
                    q, r = q + dq, r + dr
        ring += 1
    return pts[:n]


class _Maker:
    """Builds copies for one operator run, sharing one primer mesh per cartridge."""

    def __init__(self, context, s):
        self.context, self.s, self.primers = context, s, {}

    def __call__(self, cart, kind, seed, location=(0.0, 0.0, 0.0), rot_z=0.0, colls=None):
        s = self.s
        cp = variation.realize(cart, seed, kind)
        cp.dirt = min(1.0, cp.dirt * s.dirt_scale)
        cp.soot_in = min(1.0, cp.soot_in * s.soot_scale)
        cp.soot_out = min(1.0, cp.soot_out * s.soot_scale)
        primer = None  # fired cases get their own struck primer
        if kind != "fired":
            if cart.key not in self.primers:
                self.primers[cart.key] = sc.primer_mesh(cart)
            primer = self.primers[cart.key]
        colls = colls or [_collection(self.context, cart.key)]
        root = sc.make_copy(colls[0], f"{cart.key}.{kind}.{seed}", cart, cp, primer, location, rot_z, {})
        for c in colls[1:]:
            for ob in (root, *root.children):
                c.objects.link(ob)
        return root


def _roots(context):
    """Selected Gun Food copies (a selected part counts as its whole copy)."""
    out = []
    for ob in context.selected_objects:
        root = ob if ob.get("cartridge") else (ob.parent if ob.parent and ob.parent.get("cartridge") else None)
        if root and root not in out:
            out.append(root)
    return out


def _delete(root):
    meshes = [ch.data for ch in root.children if ch.type == "MESH"]
    for ch in list(root.children):
        bpy.data.objects.remove(ch)
    bpy.data.objects.remove(root)
    for me in meshes:
        if me.users == 0:
            bpy.data.meshes.remove(me)


def _select(context, objs):
    for ob in context.selected_objects:
        ob.select_set(False)
    for ob in objs:
        ob.select_set(True)
    if objs:
        context.view_layer.objects.active = objs[-1]


def _new_seed(s):
    return random.randrange(1 << 30) if s.random_seed else s.seed


class GUNFOOD_OT_add(bpy.types.Operator):
    bl_idname = "gunfood.add_cartridges"
    bl_label = "Add Cartridges"
    bl_description = "Add seeded copies of the chosen cartridge at the 3D cursor"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.gun_food
        found = _carts_for(self, s, [s.cartridge])
        if found is None:
            return {"CANCELLED"}
        cart = found[s.cartridge]
        make = _Maker(context, s)
        base_seed = _new_seed(s)
        dia = cart.max_dia + (0.3 if s.kind == "fired" else 0.0)
        pitch = (dia + (0.15 if s.arrangement == "HEX" else 1.0)) * MM
        origin = context.scene.cursor.location.copy()
        rng = random.Random(base_seed)
        made = []
        for i, (dx, dy) in enumerate(_offsets(s.count, pitch, s.arrangement)):
            seed = variation.copy_seed(base_seed, cart.key, s.kind, i)
            made.append(make(cart, s.kind, seed, origin + Vector((dx, dy, 0.0)), rng.uniform(0, 2 * math.pi)))
        _select(context, made)
        self.report({"INFO"}, f"Added {len(made)} {cart.name} ({s.kind}), seed {base_seed}")
        return {"FINISHED"}


class GUNFOOD_OT_reroll(bpy.types.Operator):
    bl_idname = "gunfood.reroll"
    bl_label = "Re-roll Selected"
    bl_description = "Rebuild the selected copies with new seeds, keeping their placement"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(_roots(context))

    def execute(self, context):
        s = context.scene.gun_food
        roots = _roots(context)
        found = _carts_for(self, s, {r["cartridge"] for r in roots})
        if found is None:
            return {"CANCELLED"}
        make = _Maker(context, s)
        rng = random.Random(_new_seed(s))
        made = []
        for root in roots:
            cart, kind = found[root["cartridge"]], root.get("kind", "loaded")
            parent, inv, basis = root.parent, root.matrix_parent_inverse.copy(), root.matrix_basis.copy()
            colls = list(root.users_collection)
            _delete(root)
            new = make(cart, kind, rng.randrange(1 << 30), colls=colls)
            new.parent, new.matrix_parent_inverse, new.matrix_basis = parent, inv, basis
            made.append(new)
        _select(context, made)
        self.report({"INFO"}, f"Re-rolled {len(made)} copies")
        return {"FINISHED"}


class GUNFOOD_OT_duplicate(bpy.types.Operator):
    bl_idname = "gunfood.duplicate_variation"
    bl_label = "Duplicate as New Variation"
    bl_description = "Copy the selected cartridges, each copy a new seeded sample, offset along X"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(_roots(context))

    def execute(self, context):
        s = context.scene.gun_food
        roots = _roots(context)
        found = _carts_for(self, s, {r["cartridge"] for r in roots})
        if found is None:
            return {"CANCELLED"}
        make = _Maker(context, s)
        rng = random.Random(_new_seed(s))
        made = []
        for root in roots:
            cart, kind = found[root["cartridge"]], root.get("kind", "loaded")
            new = make(cart, kind, rng.randrange(1 << 30), colls=list(root.users_collection))
            shift = Matrix.Translation(Vector((cart.max_dia + 1.0, 0.0, 0.0)) * MM)
            new.matrix_world = shift @ root.matrix_world
            made.append(new)
        _select(context, made)
        self.report({"INFO"}, f"Added {len(made)} new variations")
        return {"FINISHED"}


class GUNFOOD_OT_catalog(bpy.types.Operator):
    bl_idname = "gunfood.build_catalog"
    bl_label = "Add Catalog"
    bl_description = "Add every cartridge as loaded / new / fired groups, the layout build.py makes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.gun_food
        width, depth, stats = sc.build_layout(list(carts().values()), seed=_new_seed(s))
        self.report({"INFO"}, f"Added {len(stats['copies'])} copies ({width:.0f} x {depth:.0f} mm)")
        return {"FINISHED"}


class GUNFOOD_OT_tune_eevee(bpy.types.Operator):
    bl_idname = "gunfood.tune_eevee"
    bl_label = "Tune EEVEE for Small Parts"
    bl_description = (
        "Screen-traced reflections with a 2 mm trace thickness, shadows on, fast GI off. "
        "The 0.2 m default thickness smears copper beside millimetre-sized parts"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        sc.configure_eevee(context.scene)
        self.report({"INFO"}, "EEVEE tuned for small metal parts")
        return {"FINISHED"}


class GUNFOOD_PT_main(bpy.types.Panel):
    bl_label = "Cartridges"
    bl_idname = "GUNFOOD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Gun Food"

    def draw(self, context):
        s = context.scene.gun_food
        col = self.layout.column(align=False)
        col.prop(s, "cartridge")
        col.prop(s, "kind")
        row = col.row(align=True)
        row.prop(s, "count")
        row.prop(s, "arrangement", text="")
        row = col.row(align=True)
        row.prop(s, "random_seed")
        sub = row.row(align=True)
        sub.enabled = not s.random_seed
        sub.prop(s, "seed")
        row = col.row(align=True)
        row.prop(s, "dirt_scale", slider=True)
        row.prop(s, "soot_scale", slider=True)
        col.operator(GUNFOOD_OT_add.bl_idname, icon="ADD")
        col.separator()
        box = col.box()
        box.label(text="Selected copies")
        box.operator(GUNFOOD_OT_reroll.bl_idname, icon="FILE_REFRESH")
        box.operator(GUNFOOD_OT_duplicate.bl_idname, icon="DUPLICATE")
        col.separator()
        col.operator(GUNFOOD_OT_catalog.bl_idname, icon="OUTLINER_COLLECTION")
        col.operator(GUNFOOD_OT_tune_eevee.bl_idname, icon="SHADING_RENDERED")


class GUNFOOD_PT_overrides(bpy.types.Panel):
    bl_label = "Spec Overrides"
    bl_idname = "GUNFOOD_PT_overrides"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Gun Food"
    bl_parent_id = "GUNFOOD_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.gun_food, "use_overrides", text="")

    def draw(self, context):
        s = context.scene.gun_food
        cart = carts().get(s.cartridge)
        col = self.layout.column()
        col.enabled = s.use_overrides
        col.label(text="Maximums; copies still vary inside the tolerances")
        if s.ov_key != s.cartridge:
            col.label(text="Tick the box to load this cartridge's values", icon="INFO")
        for prop, _, _ in OVERRIDES:
            if prop == "ov_oal" and cart and cart.seats_on_cannelure:
                col.label(text="Overall length: set by the bullet's cannelure", icon="INFO")
                continue
            if prop == "ov_crimp" and cart and cart.crimp == "none":
                continue
            col.prop(s, prop)
        col.operator("gunfood.reset_overrides", icon="LOOP_BACK")


class GUNFOOD_OT_reset_overrides(bpy.types.Operator):
    bl_idname = "gunfood.reset_overrides"
    bl_label = "Reset to Spec"
    bl_description = "Copy the chosen cartridge's spec values back into the override fields"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _fill_overrides(context.scene.gun_food, context)
        return {"FINISHED"}


CLASSES = (
    GunFoodSettings,
    GUNFOOD_OT_add,
    GUNFOOD_OT_reroll,
    GUNFOOD_OT_duplicate,
    GUNFOOD_OT_catalog,
    GUNFOOD_OT_tune_eevee,
    GUNFOOD_OT_reset_overrides,
    GUNFOOD_PT_main,
    GUNFOOD_PT_overrides,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gun_food = PointerProperty(type=GunFoodSettings)


def unregister():
    del bpy.types.Scene.gun_food
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
