"""Build the cartridge scene: seeded copies, grouped layout, studio, checks and renders."""

from __future__ import annotations

import math
import random

import bpy
import numpy as np
from mathutils import Vector

from .. import profiles, variation
from .materials import ground_material, label_material, metal_material, paint_material, studio_world
from .mesh import (
    BULLET_SEGMENTS,
    CASE_SEGMENTS,
    FINE_STEP,
    MM,
    PRIMER_SEGMENTS,
    apply_boolean,
    bullet_cavity,
    case_cavity,
    finish_shading,
    edge_attr,
    flatten_head,
    headstamp_tools,
    lathe,
    micro_relief,
    paint_tip,
    press_flats,
    primer_attrs,
    scratch_lines,
)

GAP = 10.0  # mm between groups
CLEARANCE = 0.15  # mm between neighbours inside a group
GROUP_KINDS = ("loaded", "case", "fired")
REFINE = 0.6  # mm, longest profile segment (dents need vertices to move)
GROUND_DROP = 0.1  # mm the ground sits below z=0, so heads and labels don't z-fight with it


# ---------------------------------------------------------------- scene setup


def reset_scene(engine: str = "eevee"):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for datas in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.curves, bpy.data.collections):
        for block in list(datas):
            datas.remove(block)
    scene = bpy.context.scene
    scene.name = "Cartridges"
    us = scene.unit_settings
    us.system = "METRIC"
    us.scale_length = 1.0
    us.length_unit = "MILLIMETERS"
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.film_transparent = False
    for name in dir(scene.render):  # no file path, date or render time written into images
        if name.startswith("use_stamp"):
            try:
                setattr(scene.render, name, False)
            except (AttributeError, TypeError):
                pass
    configure_cycles(scene)
    configure_eevee(scene)
    scene.render.engine = "CYCLES" if engine == "cycles" else "BLENDER_EEVEE"
    studio_world()
    return scene


def _set(obj, name, value):
    try:
        setattr(obj, name, value)
    except (AttributeError, TypeError, ValueError):
        pass


def configure_eevee(scene):
    ee = scene.eevee
    _set(ee, "taa_render_samples", 64)
    _set(ee, "use_raytracing", True)  # metals need traced reflections of the ground and their neighbours
    _set(ee, "ray_tracing_method", "SCREEN")
    rto = getattr(ee, "ray_tracing_options", None)
    if rto:
        _set(rto, "resolution_scale", "1")
        _set(rto, "trace_max_roughness", 0.5)
        _set(rto, "screen_trace_quality", 0.5)
        _set(rto, "screen_trace_thickness", 0.002)  # default 0.2 m treats rays passing behind small parts as hits
    _set(ee, "use_shadows", True)
    _set(ee, "shadow_ray_count", 2)
    _set(ee, "shadow_step_count", 6)
    _set(ee, "use_fast_gi", False)  # its horizon scan leaves halos beside small bright parts


def configure_cycles(scene):
    cy = scene.cycles
    cy.samples = 128
    cy.adaptive_threshold = 0.02
    cy.use_denoising = True
    cy.denoiser = "OPENIMAGEDENOISE"


def use_gpu() -> str:
    """Cycles: use the first GPU backend that has a device; fall back to CPU."""
    scene = bpy.context.scene
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == backend]
        if gpus:
            for d in prefs.devices:
                d.use = d.type == backend
            scene.cycles.device = "GPU"
            return f"{backend}: {', '.join(d.name for d in gpus)}"
    scene.cycles.device = "CPU"
    return "CPU"


def _collection(name, parent=None):
    coll = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(coll)
    return coll


# ---------------------------------------------------------------- per-copy meshes


def _fine_segments(base: int, radius: float) -> int:
    """Meridians for about FINE_STEP between them at ``radius`` (mm), a multiple of 8."""
    return max(base, 8 * math.ceil(2 * math.pi * radius / FINE_STEP / 8))


def case_mesh(cart, cp: variation.Copy, name: str) -> tuple[bpy.types.Mesh, str]:
    """Unique case mesh for one copy: sampled dimensions, crimp, dents, the maker's headstamp."""
    c = cp.case
    # flat spots and fine scratches need a fine mesh to move (all of the outside: patches of
    # fine mesh show their seams in the reflections)
    fine = bool(cp.case_scratches) or any(f.fine for f in cp.case_flats)
    prof = profiles.refine(profiles.case_profile(cp.case, cp.crimp), FINE_STEP if fine else REFINE, outside_only=True)
    segs = _fine_segments(CASE_SEGMENTS, max(c.rim_dia, c.base_dia) / 2) if fine else CASE_SEGMENTS
    me = lathe(name, prof, segs, offset=lambda r, z, t: variation.case_offset(cp, r, z, t))
    edges = (0.0, c.rim_thickness, c.groove_top or c.rim_thickness, c.length)
    micro_relief(me, cp.micro, variation.copy_seed(cp.seed, "micro-case"), edges)
    press_flats(me, cp.case_flats)
    scratch_lines(me, cp.case_scratches)
    me.materials.append(metal_material(cp.case.material))
    tools, region = headstamp_tools(cart, cp, random.Random(cp.headstamp_seed))
    solver = "none"
    if tools:
        tmp = bpy.data.objects.new("_case", me)
        bpy.context.scene.collection.objects.link(tmp)
        solver = "/".join(sorted({apply_boolean(tmp, tool, op) for tool, op in tools}))
        me = tmp.data
        bpy.data.objects.remove(tmp)
        finish_shading(me)
        flatten_head(me, region[3] if region else 0.3)
    case_cavity(me, cp.case, region)
    edge_attr(me)
    me.name = name
    return me, solver


def bullet_mesh(cp: variation.Copy, name: str) -> bpy.types.Mesh:
    fine = bool(cp.bullet_scratches) or any(f.fine for f in cp.bullet_flats)  # see case_mesh
    prof = profiles.refine(profiles.bullet_profile(cp.bullet), FINE_STEP if fine else REFINE * 1.2, outside_only=True)
    segs = _fine_segments(BULLET_SEGMENTS, cp.bullet.dia / 2) if fine else BULLET_SEGMENTS
    me = lathe(name, prof, segs, offset=(lambda r, z, t: variation.bullet_offset(cp, r, z, t)) if cp.bullet_dents else None)
    soft = {"copper": 1.4, "lead": 1.8}.get(cp.bullet.jacket, 1.0)  # plated and bare lead take knocks easily
    micro_relief(me, cp.micro * soft, variation.copy_seed(cp.seed, "micro-bullet"), (0.0, cp.bullet.length))
    press_flats(me, cp.bullet_flats)
    scratch_lines(me, cp.bullet_scratches)
    me.materials.append(metal_material(cp.bullet.jacket))
    me.materials.append(metal_material(cp.bullet.core))
    if cp.lot and cp.lot.tip != "none" and cp.tip_length > 0:
        me.materials.append(paint_material(cp.lot.tip, cp.lot.tip_rgb))
        paint_tip(me, cp.bullet, cp.tip_length, 2)
    bullet_cavity(me, cp.bullet)
    edge_attr(me)
    return me


def primer_mesh(cart, cp: variation.Copy | None = None, name: str | None = None, metal: str | None = None) -> bpy.types.Mesh | None:
    """An unfired primer (shareable), or with ``cp`` a fired one with its firing-pin crater."""
    if cart.case.rimfire:
        return None
    strike = cp.primer_strike if cp else None
    metal = metal or (cp.case.primer_cup if cp else cart.case.primer_cup)
    me = lathe(name or f"{cart.key}.primer.{metal}", profiles.primer_profile(cart.case, strike=strike), PRIMER_SEGMENTS)
    me.materials.append(metal_material(metal))
    primer_attrs(me, cart.case)
    edge_attr(me)
    return me


def shared_primer(primers: dict | None, cart, metal: str):
    """One unfired primer mesh per cartridge and metal, kept in ``primers``."""
    if cart.case.rimfire:
        return None
    if primers is None:
        return primer_mesh(cart, metal=metal)
    key = (cart.key, metal)
    if key not in primers:
        primers[key] = primer_mesh(cart, metal=metal)
    return primers[key]


def make_copy(coll, name, cart, cp: variation.Copy, primers: dict | None, location, rot_z, stats):
    """One item: a loaded round, a primed empty case, or a bullet.

    ``primers`` caches the shared unfired primer meshes (see ``shared_primer``); fired
    cases get their own struck primer.
    """
    root = bpy.data.objects.new(name, None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.002
    root.location = location
    root.rotation_euler = (0.0, 0.0, rot_z)
    for k, v in cp.labels().items():
        root[k] = v
    root["cartridge"] = cart.key
    coll.objects.link(root)

    def child(me, part, z=0.0, rot=(0.0, 0.0, 0.0)):
        ob = bpy.data.objects.new(f"{name}.{part}", me)
        ob.parent = root
        ob.location = (0.0, 0.0, z)
        ob.rotation_euler = rot
        ob["gf_age"] = cp.age  # material drivers, see materials.py
        ob["gf_wear"] = cp.wear
        ob["gf_grime"] = cp.grime
        coll.objects.link(ob)
        return ob

    if cp.kind in ("loaded", "case", "fired"):
        me, solver = case_mesh(cart, cp, f"{name}.case")
        stats.setdefault("headstamp", {}).setdefault(cart.key, set()).add(solver)
        case_ob = child(me, "case")
        # material drivers in the object colour (see materials.py): dirt, soot in, soot out, anneal
        anneal = cp.lot.anneal if cp.lot else 0.0
        case_ob.color = (cp.dirt, cp.soot_in, cp.soot_out, anneal)
        case_ob["gf_iris"] = 1.0 if cp.lot and cp.lot.anneal_colour == "rainbow" else 0.0
        if cp.kind == "fired" and not cart.case.rimfire:
            primer = primer_mesh(cart, cp, f"{name}.primer")
        else:
            primer = shared_primer(primers, cart, cp.case.primer_cup)
        if primer:
            pr = child(primer, "primer")
            pr.color = (cp.dirt * (0.6 if cp.kind == "fired" else 1.0), 0.0, 0.0, 0.0)
            pr["gf_seal"] = list(cp.lot.sealant_rgb) if cp.lot else [0.0, 0.0, 0.0]
            pr["gf_smear"] = cp.lot.smear if cp.lot else 0.0
    if cp.kind == "loaded":
        tilt, az = math.radians(cp.runout[0]), cp.runout[1]
        bl = child(bullet_mesh(cp, f"{name}.bullet"), "bullet", (cp.case.length - cp.seat_depth) * MM, (tilt * math.cos(az), tilt * math.sin(az), 0.0))
        bl.color = (cp.dirt, 0.0, 0.0, 0.0)
        bl["gf_age"] = cp.bullet_age
    if cp.kind == "bullet":
        bl = child(bullet_mesh(cp, f"{name}.bullet"), "bullet")
        bl.color = (cp.dirt, 0.0, 0.0, 0.0)
        bl["gf_age"] = cp.bullet_age
    stats.setdefault("copies", []).append((cart, cp, root))
    return root


# ---------------------------------------------------------------- layout


def _group_dia(cart, kind):
    if kind == "loaded":
        return cart.max_dia
    if kind == "case":
        return max(cart.case.rim_dia, cart.case.base_dia)
    if kind == "fired":  # expanded to the chamber, plus out-of-round
        return max(cart.case.rim_dia, cart.case.base_dia) + 0.3
    return cart.bullet.dia


def _hex7(pitch):
    return [(0.0, 0.0)] + [(pitch * math.cos(math.radians(60 * i)), pitch * math.sin(math.radians(60 * i))) for i in range(6)]


def _group_extent(dia):
    pitch = dia + CLEARANCE
    return 2 * pitch + dia, 2 * pitch * math.sin(math.radians(60)) + dia


def build_layout(carts, seed=1, columns=3, condition=None):
    """Tight hex groups of 7 per kind (loaded rounds, new primed cases, fired cases), GAP mm apart.

    Every copy is a separate seeded sample (``variation.realize``), so no two are identical,
    and the same ``seed`` always rebuilds the same scene.
    """
    rng = random.Random(seed)
    root = _collection("Cartridges")
    labels = _collection("Labels")
    labels.hide_render = True
    stats: dict = {}

    blocks = []
    for cart in carts:
        sizes = [_group_extent(_group_dia(cart, k)) for k in GROUP_KINDS]
        blocks.append((cart, sizes, sum(w for w, _ in sizes) + GAP * (len(sizes) - 1), max(d for _, d in sizes)))
    columns = max(1, min(columns, len(blocks)))
    rows = [blocks[i : i + columns] for i in range(0, len(blocks), columns)]
    col_w = [max(r[c][2] for r in rows if c < len(r)) for c in range(columns)]
    row_d = [max(b[3] for b in r) for r in rows]
    total_w = sum(col_w) + GAP * (columns - 1)
    total_d = sum(row_d) + GAP * (len(rows) - 1)

    y_top = total_d / 2
    for ri, row in enumerate(rows):
        y_c = y_top - row_d[ri] / 2
        x_left = -total_w / 2
        for ci, (cart, sizes, _block_w, _) in enumerate(row):
            coll = _collection(cart.key, root)
            primers: dict = {}
            x = x_left
            for kind, (gw, _gd) in zip(GROUP_KINDS, sizes):
                dia = _group_dia(cart, kind)
                cx = x + gw / 2
                for i, (dx, dy) in enumerate(_hex7(dia + CLEARANCE)):
                    cp = variation.realize(cart, variation.copy_seed(seed, cart.key, kind, i), kind, condition)
                    loc = Vector(((cx + dx) * MM, (y_c + dy) * MM, 0.0))
                    make_copy(coll, f"{cart.key}.{kind}.{i}", cart, cp, primers, loc, rng.uniform(0, 2 * math.pi), stats)
                x += gw + GAP
            _label(labels, cart.name, (x_left + 1.0) * MM, (y_c - row_d[ri] / 2 - 2.0) * MM)
            x_left += col_w[ci] + GAP
        y_top -= row_d[ri] + GAP
    return total_w, total_d, stats


def _label(coll, text, x, y):
    cu = bpy.data.curves.new(f"label {text}", type="FONT")
    cu.body = text
    cu.size = 0.004
    cu.align_y = "TOP"
    cu.materials.append(label_material())
    ob = bpy.data.objects.new(f"label {text}", cu)
    ob.color = (0.0, 0.0, 0.0, 1.0)
    ob.location = (x, y, 0.0)
    coll.objects.link(ob)


# ---------------------------------------------------------------- studio


def add_studio(width_mm, depth_mm):
    coll = _collection("Studio")
    size = max(width_mm, depth_mm) * 3 * MM
    bpy.ops.mesh.primitive_plane_add(size=size)
    ground = bpy.context.active_object
    ground.name = "Ground"
    ground.location.z = -GROUND_DROP * MM
    ground.data.materials.append(ground_material())
    _move(ground, coll)

    def area(name, loc, power, sz, colour=(1, 1, 1)):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = power
        light.size = sz
        light.color = colour
        light.use_shadow = True
        ob = bpy.data.objects.new(name, light)
        ob.location = loc
        _aim(ob, Vector((0, 0, 0)))
        coll.objects.link(ob)
        return ob

    s = max(width_mm, depth_mm) * MM
    area("Key", (-0.7 * s, -1.0 * s, 1.2 * s), 18.0, 0.6 * s, (1.0, 0.97, 0.93))
    area("Fill", (1.1 * s, -0.5 * s, 0.7 * s), 5.0, 0.8 * s, (0.92, 0.95, 1.0))
    area("Rim", (0.0, 1.2 * s, 0.9 * s), 12.0, 0.5 * s)

    cam_data = bpy.data.cameras.new("Cam_Overview")
    cam_data.lens = 50
    cam = bpy.data.objects.new("Cam_Overview", cam_data)
    half_fov = math.atan(cam_data.sensor_width / 2 / cam_data.lens)
    dist = (width_mm * MM / 2) / math.tan(half_fov) * 1.25
    elev = math.radians(42)
    cam.location = (0.0, -dist * math.cos(elev), dist * math.sin(elev))
    _aim(cam, Vector((0, 0, 0.012)))
    coll.objects.link(cam)
    bpy.context.scene.camera = cam
    return coll


def _move(ob, coll):
    for c in ob.users_collection:
        c.objects.unlink(ob)
    coll.objects.link(ob)


def _aim(ob, target):
    d = target - Vector(ob.location)
    if abs(d.normalized().z) > 0.9999:  # straight down: keep +Y as image up
        ob.rotation_euler = (0.0, 0.0, 0.0) if d.z < 0 else (math.pi, 0.0, 0.0)
    else:
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


# ---------------------------------------------------------------- checks


def _rz(me):
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) / MM
    return np.hypot(co[:, 0], co[:, 1]), co[:, 2]


def dimension_report(carts, stats) -> str:
    """Measure every generated copy and check it against its SAAMI band."""
    rows = [
        "| Cartridge | Copies | Case length (band) | Rim dia (band) | Overall length (SAAMI) | Bullet dia (band) | Out of band | Headstamp |",
        "|---|---|---|---|---|---|---|---|",
    ]
    total_bad = 0
    for cart in carts:
        k = cart.case
        lens, rims, oals, bdias = [], [], [], []
        bad = 0
        n = 0
        for c2, cp, root in stats.get("copies", []):
            if c2.key != cart.key or cp.kind == "fired":  # fired brass has grown to the chamber
                continue
            n += 1
            parts = {ob.name.rsplit(".", 1)[1]: ob for ob in root.children}
            if "case" in parts:
                r, z = _rz(parts["case"].data)
                length = float(z.max())
                rim = 2 * float(r[z < cp.case.rim_thickness].max())
                lens.append(length)
                rims.append(rim)
                bad += not (k.length - cart.tol("length_tol") - 1e-3 <= length <= k.length + 1e-3)
                bad += not (k.rim_dia - cart.tol("rim_dia_tol") - 1e-3 <= rim <= k.rim_dia + 1e-3)
            if "bullet" in parts:
                r, z = _rz(parts["bullet"].data)
                bdia = 2 * float(r.max())
                bdias.append(bdia)
                bad += not (cart.bullet.dia - cart.bullet.dia_tol - 1e-3 <= bdia <= cart.bullet.dia + 1e-3)
                if cp.kind == "loaded":
                    oal = parts["bullet"].location.z / MM + float(z.max())
                    oals.append(oal)
                    bad += not (cart.oal_min - 1e-3 <= oal <= cart.oal_max + 1e-3)
        total_bad += bad

        def span(vals, lo, hi):
            return f"{min(vals):.3f}–{max(vals):.3f} ({lo:.2f}–{hi:.2f})" if vals else "—"

        rows.append(
            f"| {cart.name} | {n} | {span(lens, k.length - cart.tol('length_tol'), k.length)} "
            f"| {span(rims, k.rim_dia - cart.tol('rim_dia_tol'), k.rim_dia)} | {span(oals, cart.oal_min, cart.oal_max)} "
            f"| {span(bdias, cart.bullet.dia - cart.bullet.dia_tol, cart.bullet.dia)} | {bad} "
            f"| {', '.join(sorted(stats.get('headstamp', {}).get(cart.key, {'none'})))} |"
        )
    rows += ["", f"Measured from the generated meshes, mm. Copies outside their band: {total_bad}."]
    return "\n".join(rows)


# ---------------------------------------------------------------- renders


def render(path, samples=None):
    scene = bpy.context.scene
    if samples:
        scene.cycles.samples = samples
    jpeg = path.suffix.lower() in (".jpg", ".jpeg")
    scene.render.image_settings.file_format = "JPEG" if jpeg else "PNG"
    if jpeg:
        scene.render.image_settings.quality = 90
    bpy.context.view_layer.update()  # parts made after the last render need their object colour synced
    bpy.ops.render.render()
    bpy.data.images["Render Result"].save_render(filepath=str(path.resolve()))


def render_details(carts, out_dir, seed=1):
    """Side-view lineup and head-on headstamp row, built in a temporary collection."""
    scene = bpy.context.scene
    main = bpy.data.collections["Cartridges"]
    main.hide_render = True
    temp = _collection("_detail")
    stats: dict = {}
    spacing = 6.0

    x = 0.0
    for cart in carts:
        x += cart.max_dia / 2
        cp = variation.realize(cart, variation.copy_seed(seed, cart.key, "lineup"), "loaded")
        make_copy(temp, f"_line.{cart.key}", cart, cp, None, (x * MM, 0, 0), 0.0, stats)
        x += cart.max_dia / 2 + spacing
    width = x - spacing
    tallest = max(c.oal_max for c in carts)
    for ob in temp.objects:
        if ob.parent is None:
            ob.location.x -= width / 2 * MM
    cam = _ortho_cam("_cam_side", (0, -0.5, tallest / 2 * MM), (0, 0, tallest / 2 * MM), max(width, tallest * 2) * 1.08 * MM)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = 2000, 1000
    render(out_dir / "lineup.jpg", samples=96)

    for ob in list(temp.objects):
        bpy.data.objects.remove(ob)
    x = 0.0
    for cart in carts:
        d = max(cart.case.rim_dia, cart.case.base_dia)
        x += d / 2
        cp = variation.realize(cart, variation.copy_seed(seed, cart.key, "head"), "case")
        root = make_copy(temp, f"_head.{cart.key}", cart, cp, None, (x * MM, 0, cp.case.length * MM), 0.0, stats)
        root.rotation_euler = (math.pi, 0.0, math.pi)  # head up, headstamp upright in the top view
        x += d / 2 + 3.0
    width = x - 3.0
    for ob in temp.objects:
        if ob.parent is None:
            ob.location.x -= width / 2 * MM
    top = max(c.case.length for c in carts)
    rake = bpy.data.objects.new("_rake", bpy.data.lights.new("_rake", "SUN"))
    rake.data.energy = 3.0
    rake.data.angle = math.radians(1.5)
    rake.rotation_euler = (math.radians(75), 0.0, math.radians(-35))  # low, grazing light shows the stamping
    temp.objects.link(rake)
    cam = _ortho_cam("_cam_top", (0, 0, (top + 50) * MM), (0, 0, 0), width * 1.04 * MM)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = 3000, 360
    render(out_dir / "headstamps.jpg", samples=96)

    # fired cases lying on their sides, mouths toward the camera: soot inside, dirt outside
    for ob in list(temp.objects):
        if ob.type != "CAMERA":
            bpy.data.objects.remove(ob)
    turn = math.radians(40)  # mouths angled toward the camera so the inside shows
    x = 0.0
    for cart in carts:
        d = max(cart.case.rim_dia, cart.case.base_dia) + 0.3
        foot = max(d, cart.case.length * math.sin(turn))
        x += foot / 2
        cp = variation.realize(cart, variation.copy_seed(seed, cart.key, "fired-detail"), "fired")
        # lying on its side; the head sits back and to the left, the mouth forward and right
        cx, cy = x - cart.case.length / 2 * math.sin(turn), cart.case.length / 2 * math.cos(turn)
        root = make_copy(temp, f"_fired.{cart.key}", cart, cp, None, (cx * MM, cy * MM, d / 2 * MM), 0.0, stats)
        root.rotation_euler = (math.pi / 2, 0.0, turn)  # axis runs (+sin, -cos): mouth forward and right
        x += foot / 2 + 5.0
    width = x - 5.0
    for ob in temp.objects:
        if ob.parent is None and ob.type == "EMPTY":
            ob.location.x -= width / 2 * MM
    cam = _ortho_cam("_cam_fired", (0, -1.0, 0.75), (0, 0.0, 0.004), width * 1.08 * MM)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = 2400, 1000
    render(out_dir / "fired.jpg", samples=96)

    main.hide_render = False
    scene.camera = bpy.data.objects["Cam_Overview"]
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080


def _ortho_cam(name, loc, target, ortho_scale):
    """Near-orthographic view from a long lens far away.

    A true orthographic camera breaks EEVEE's screen-space reflections (copper smears beside
    the parts), so this backs a 400 mm lens off until ``ortho_scale`` fills the frame.
    """
    data = bpy.data.cameras.new(name)
    data.lens = 400
    data.clip_start = 0.01
    data.clip_end = 100
    dist = (ortho_scale / 2) / (data.sensor_width / 2 / data.lens)
    loc, target = Vector(loc), Vector(target)
    cam = bpy.data.objects.new(name, data)
    cam.location = target + (loc - target).normalized() * dist
    _aim(cam, target)
    bpy.data.collections["_detail"].objects.link(cam)
    return cam
