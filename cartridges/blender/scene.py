"""Build the cartridge scene: parts, grouped layout, studio, cameras, checks and renders."""

from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

from .. import profiles
from .materials import ground_material, metal_material, studio_world
from .mesh import MM, apply_boolean, headstamp_tool, lathe

GAP = 10.0  # mm between groups
CLEARANCE = 0.15  # mm between neighbours inside a group
GROUP_KINDS = ("loaded", "case", "bullet")


# ---------------------------------------------------------------- scene setup


def reset_scene():
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
    scene.render.engine = "CYCLES"
    cy = scene.cycles
    cy.samples = 128
    cy.adaptive_threshold = 0.02
    cy.use_denoising = True
    cy.denoiser = "OPENIMAGEDENOISE"
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.film_transparent = False
    # Don't write render metadata (file path, date, render time) into images.
    for name in dir(scene.render):
        if name.startswith("use_stamp"):
            try:
                setattr(scene.render, name, False)
            except (AttributeError, TypeError):
                pass
    studio_world()
    return scene


def use_gpu() -> str:
    """Use the first GPU backend that has a device; fall back to CPU."""
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


# ---------------------------------------------------------------- parts


def make_parts(cart):
    """Shared mesh data for one cartridge: case (with headstamp), primer, bullet."""
    case_p, bullet_p, primer_p, bullet_z = profiles.cartridge_profiles(cart)
    case_me = lathe(f"{cart.key}_case", case_p, segments=128)
    case_me.materials.append(metal_material(cart.case.material))
    solver = "none"
    tool, op = headstamp_tool(cart)
    if tool:
        tmp = bpy.data.objects.new("_case", case_me)
        bpy.context.scene.collection.objects.link(tmp)
        solver = apply_boolean(tmp, tool, op)
        case_me = tmp.data
        bpy.data.objects.remove(tmp)
    bullet_me = lathe(f"{cart.key}_bullet", bullet_p, segments=96)
    bullet_me.materials.append(metal_material(cart.bullet.jacket))
    bullet_me.materials.append(metal_material(cart.bullet.core))
    primer_me = None
    if primer_p:
        primer_me = lathe(f"{cart.key}_primer", primer_p, segments=64)
        primer_me.materials.append(metal_material(cart.case.primer_cup))
    return {"case": case_me, "bullet": bullet_me, "primer": primer_me, "bullet_z": bullet_z, "headstamp": solver}


def make_round(coll, name, cart, parts, kind, location, rot_z, rng):
    """One item: a loaded round, a primed empty case, or a bullet. Children share mesh data."""
    root = bpy.data.objects.new(name, None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.002
    root.location = location
    root.rotation_euler = (0.0, 0.0, rot_z)
    coll.objects.link(root)

    def child(me, part, z=0.0):
        ob = bpy.data.objects.new(f"{name}.{part}", me)
        ob.parent = root
        ob.location = (0.0, 0.0, z)
        coll.objects.link(ob)
        return ob

    if kind in ("loaded", "case"):
        case_ob = child(parts["case"], "case")
        if cart.case.bottleneck:  # annealing stain on neck and shoulder (see materials.py)
            case_ob["anneal_z0"] = cart.case.shoulder_start - 6.0
            case_ob["anneal_z1"] = cart.case.shoulder_start - 1.5
            case_ob["anneal_amt"] = rng.uniform(0.15, 0.55)
        if parts["primer"]:
            child(parts["primer"], "primer")
    if kind == "loaded":
        child(parts["bullet"], "bullet", parts["bullet_z"] * MM)
    if kind == "bullet":
        child(parts["bullet"], "bullet")
    return root


# ---------------------------------------------------------------- layout


def _group_dia(cart, kind):
    if kind == "loaded":
        return cart.max_dia
    if kind == "case":
        return max(cart.case.rim_dia, cart.case.base_dia)
    return cart.bullet.dia


def _hex7(pitch):
    return [(0.0, 0.0)] + [(pitch * math.cos(math.radians(60 * i)), pitch * math.sin(math.radians(60 * i))) for i in range(6)]


def _group_extent(dia):
    pitch = dia + CLEARANCE
    return 2 * pitch + dia, 2 * pitch * math.sin(math.radians(60)) + dia  # width (x), depth (y)


def build_layout(carts, parts_by_key, columns=3, seed=7):
    """Tight hex groups of 7 per kind, three groups per cartridge, GAP mm apart everywhere."""
    rng = random.Random(seed)
    root = _collection("Cartridges")
    labels = _collection("Labels")
    labels.hide_render = True

    blocks = []
    for cart in carts:
        sizes = [_group_extent(_group_dia(cart, k)) for k in GROUP_KINDS]
        blocks.append((cart, sizes, sum(w for w, _ in sizes) + GAP * (len(sizes) - 1), max(d for _, d in sizes)))
    rows = [blocks[i : i + columns] for i in range(0, len(blocks), columns)]
    col_w = [max(r[c][2] for r in rows if c < len(r)) for c in range(columns)]
    row_d = [max(b[3] for b in r) for r in rows]
    total_w = sum(col_w) + GAP * (columns - 1)
    total_d = sum(row_d) + GAP * (len(rows) - 1)

    y_top = total_d / 2
    for ri, row in enumerate(rows):
        y_c = y_top - row_d[ri] / 2
        x_left = -total_w / 2
        for ci, (cart, sizes, block_w, _) in enumerate(row):
            coll = _collection(cart.key, root)
            parts = parts_by_key[cart.key]
            x = x_left
            for kind, (gw, _gd) in zip(GROUP_KINDS, sizes):
                dia = _group_dia(cart, kind)
                cx = x + gw / 2
                for i, (dx, dy) in enumerate(_hex7(dia + CLEARANCE)):
                    loc = Vector(((cx + dx) * MM, (y_c + dy) * MM, 0.0))
                    make_round(coll, f"{cart.key}.{kind}.{i}", cart, parts, kind, loc, rng.uniform(0, 2 * math.pi), rng)
                x += gw + GAP
            _label(labels, cart.name, (x_left + 1.0) * MM, (y_c - row_d[ri] / 2 - 2.0) * MM)
            x_left += col_w[ci] + GAP
        y_top -= row_d[ri] + GAP
    return total_w, total_d


def _label(coll, text, x, y):
    cu = bpy.data.curves.new(f"label {text}", type="FONT")
    cu.body = text
    cu.size = 0.004
    cu.align_y = "TOP"
    ob = bpy.data.objects.new(f"label {text}", cu)
    ob.location = (x, y, 0.0)
    coll.objects.link(ob)


# ---------------------------------------------------------------- studio


def add_studio(width_mm, depth_mm):
    coll = _collection("Studio")
    size = max(width_mm, depth_mm) * 3 * MM
    bpy.ops.mesh.primitive_plane_add(size=size)
    ground = bpy.context.active_object
    ground.name = "Ground"
    ground.data.materials.append(ground_material())
    _move(ground, coll)

    def area(name, loc, power, size, colour=(1, 1, 1)):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = power
        light.size = size
        light.color = colour
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


def measure(parts):
    """Measure the generated meshes (mm)."""
    def verts(me):
        return [(math.hypot(v.co.x, v.co.y) / MM, v.co.z / MM) for v in me.vertices]

    case = verts(parts["case"])
    bullet = verts(parts["bullet"])
    length = max(z for _, z in case)
    return {
        "case_length": length,
        "rim_dia": 2 * max(r for r, z in case if z < 2.0),
        "mouth_dia": 2 * max(r for r, z in case if length - 1.0 < z),
        "bullet_dia": 2 * max(r for r, _ in bullet),
        "bullet_length": max(z for _, z in bullet),
        "oal": parts["bullet_z"] + max(z for _, z in bullet),
    }


def dimension_report(carts, parts_by_key) -> str:
    rows = [
        "| Cartridge | Case length | Rim dia | Mouth dia | Bullet dia | OAL | Headstamp |",
        "|---|---|---|---|---|---|---|",
    ]
    worst = 0.0
    for cart in carts:
        m = measure(parts_by_key[cart.key])
        pairs = [
            (m["case_length"], cart.case.length),
            (m["rim_dia"], cart.case.rim_dia),
            (m["mouth_dia"], cart.case.mouth_dia),
            (m["bullet_dia"], cart.bullet.dia),
            (m["oal"], cart.oal),
        ]
        cells = []
        for got, want in pairs:
            worst = max(worst, abs(got - want))
            cells.append(f"{got:.3f} / {want:.2f}")
        rows.append(f"| {cart.name} | " + " | ".join(cells) + f" | {parts_by_key[cart.key]['headstamp']} |")
    rows.append("")
    rows.append(f"Measured from the generated meshes / spec value, mm. Largest difference: {worst:.4f} mm.")
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
    bpy.ops.render.render()
    bpy.data.images["Render Result"].save_render(filepath=str(path.resolve()))


def render_details(carts, parts_by_key, out_dir):
    """Side-view lineup and head-on headstamp row, built in a temporary collection."""
    scene = bpy.context.scene
    main = bpy.data.collections["Cartridges"]
    main.hide_render = True
    temp = _collection("_detail")
    rng = random.Random(1)
    spacing = 6.0

    # lineup: loaded rounds standing in a row, seen from the side
    x = 0.0
    xs = []
    for cart in carts:
        x += cart.max_dia / 2
        make_round(temp, f"_line.{cart.key}", cart, parts_by_key[cart.key], "loaded", (x * MM, 0, 0), 0.0, rng)
        xs.append(x)
        x += cart.max_dia / 2 + spacing
    width = x - spacing
    tallest = max(c.oal for c in carts)
    for ob in temp.objects:
        if ob.parent is None:
            ob.location.x -= width / 2 * MM
    cam = _ortho_cam("_cam_side", (0, -0.5, tallest / 2 * MM), (0, 0, tallest / 2 * MM), max(width, tallest * 2) * 1.08 * MM)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = 2000, 1000
    render(out_dir / "lineup.jpg", samples=96)

    # heads: cases turned over, seen from above
    for ob in list(temp.objects):
        bpy.data.objects.remove(ob)
    x = 0.0
    for cart in carts:
        d = max(cart.case.rim_dia, cart.case.base_dia)
        x += d / 2
        root = make_round(temp, f"_head.{cart.key}", cart, parts_by_key[cart.key], "case", ((x) * MM, 0, cart.case.length * MM), 0.0, rng)
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

    main.hide_render = False
    scene.camera = bpy.data.objects["Cam_Overview"]
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080


def _ortho_cam(name, loc, target, ortho_scale):
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = ortho_scale
    data.clip_start = 0.001
    cam = bpy.data.objects.new(name, data)
    cam.location = loc
    _aim(cam, Vector(target))
    bpy.data.collections["_detail"].objects.link(cam)
    return cam
