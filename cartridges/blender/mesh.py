"""Mesh construction in Blender: lathe-revolved parts, stamped headstamps, cavity attribute."""

from __future__ import annotations

import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

MM = 0.001  # Blender units are metres; specs are millimetres

CASE_SEGMENTS = 64
BULLET_SEGMENTS = 48
PRIMER_SEGMENTS = 32
STAMP_DEPTH = 0.12  # mm, how deep headstamp letters are pressed in


def lathe(name: str, profile, segments: int, offset=None) -> bpy.types.Mesh:
    """Revolve a closed ``(r, z, mat)`` profile (mm) around Z into a watertight mesh (m).

    ``offset(r, z, theta) -> mm`` moves each vertex radially (dents, out-of-round).
    """
    th = [2 * math.pi * k / segments for k in range(segments)]
    cs, sn = [math.cos(t) for t in th], [math.sin(t) for t in th]
    verts, rings = [], []
    for r, z, _ in profile:
        start = len(verts)
        if r < 1e-6:
            verts.append((0.0, 0.0, z * MM))
            rings.append((start, 1))
            continue
        for k in range(segments):
            rr = max(0.0, r + offset(r, z, th[k])) if offset else r
            verts.append((rr * MM * cs[k], rr * MM * sn[k], z * MM))
        rings.append((start, segments))

    # counter-clockwise profiles (in r-z) give outward normals with this winding
    n = len(profile)
    area = sum(profile[i][0] * profile[(i + 1) % n][1] - profile[(i + 1) % n][0] * profile[i][1] for i in range(n))
    flip = area < 0
    faces, mats = [], []
    for i in range(n):
        (a0, an), (b0, bn), mat = rings[i], rings[(i + 1) % n], profile[i][2]
        if an == 1 and bn == 1:
            continue
        for k in range(segments):
            k2 = (k + 1) % segments
            if an == 1:
                f = (a0, b0 + k2, b0 + k)
            elif bn == 1:
                f = (a0 + k, a0 + k2, b0)
            else:
                f = (a0 + k, a0 + k2, b0 + k2, b0 + k)
            faces.append(f[::-1] if flip else f)
            mats.append(mat)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set("material_index", mats)
    me.update()
    finish_shading(me)
    return me


def finish_shading(me: bpy.types.Mesh, angle: float = 40.0) -> None:
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(angle))


# ---------------------------------------------------------------- headstamps


def _glyph(ch: str, cap: float, depth: float, offset: float = 0.0) -> bpy.types.Mesh:
    """One extruded character, centred on its advance box. ``offset`` < 0 thins the strokes."""
    cu = bpy.data.curves.new("_glyph", type="FONT")
    cu.body = ch
    cu.size = cap / 0.72  # font size is the em; capitals are ~72% of it
    cu.extrude = depth / 2
    cu.offset = offset
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    ob = bpy.data.objects.new("_glyph", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return me


def _arc_layout(text, radius, cap, top: bool, rng: random.Random):
    """Where each character goes: ``[(char, matrix_mm, extra_depth)]`` and the arc span (deg)."""
    widths = []
    for ch in text:
        if ch == " ":
            widths.append(0.45 * cap)
            continue
        me = _glyph(ch, cap, 0.1)
        xs = [v.co.x for v in me.vertices] or [0.0]
        widths.append(max(max(xs) - min(xs), 0.3 * cap))
        bpy.data.meshes.remove(me)
    gap = 0.14 * cap
    total = sum(widths) + gap * (len(widths) - 1)
    span = total / radius
    placed, s = [], 0.0
    for ch, w in zip(text, widths):
        centre = s + w / 2 + rng.gauss(0, 0.025)  # hand-set type: letters wander a little
        s += w + gap
        if ch == " ":
            continue
        rad = radius + rng.gauss(0, 0.035)
        if top:  # clockwise across the top, letters' bottoms toward the centre
            alpha = math.pi / 2 + span / 2 - centre / radius
            psi = alpha - math.pi / 2
        else:  # counter-clockwise across the bottom, upright
            alpha = -math.pi / 2 - span / 2 + centre / radius
            psi = alpha + math.pi / 2
        psi += math.radians(rng.gauss(0, 2.0))
        m = Matrix.Translation((rad * math.cos(alpha), rad * math.sin(alpha), 0)) @ Matrix.Rotation(psi, 4, "Z") @ Matrix.Scale(1 + rng.gauss(0, 0.04), 4)
        placed.append((ch, m, rng.gauss(0, 0.015)))  # some letters struck deeper than others
    return placed, math.degrees(span)


def _is_manifold(me) -> bool:
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-7)
    ok = len(bm.edges) > 0 and all(e.is_manifold for e in bm.edges)
    bm.free()
    return ok


def _layer(placed, cap, depth, offset, inside, name):
    """Build one cutting/raising layer from placed characters.

    The layer spans ``depth`` mm through the head face, ``inside`` of it on the case side.
    """
    bm = bmesh.new()
    for ch, m, extra in placed:
        me = _glyph(ch, cap, depth + 2 * abs(extra), offset)
        if offset and not _is_manifold(me):
            bpy.data.meshes.remove(me)  # thinned outlines of some glyphs self-intersect; skip their core
            continue
        me.transform(Matrix.Translation((0, 0, -extra)) @ m)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    # Built reading correctly from +Z; the head faces -Z, so turn it over (a rotation, not a
    # mirror) and move it so it cuts into / rises from the head face. Then mm -> metres.
    xf = Matrix.Scale(MM, 4) @ Matrix.Translation((0, 0, inside - depth / 2)) @ Matrix.Rotation(math.pi, 4, "Y")
    bmesh.ops.transform(bm, matrix=xf, verts=bm.verts[:])
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-7)  # font caps and walls come unwelded
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def headstamp_tools(cart, case, rng: random.Random):
    """Headstamp as boolean tools: ``([(mesh, operation), ...], region)``.

    Real headstamps are pressed by a worn bunter: letters have rounded walls and soft
    bottoms. Each mark is made of two layers, a shallow full-width letter and a deeper,
    thinner core, which gives a sloped wall without the slow solver that bevelled text
    would need. ``region`` is the (r0, r1, z0, z1) box in mm around the stamp.
    Centerfire marks are pressed in (DIFFERENCE); rimfire marks are raised (UNION).
    """
    hs = cart.headstamp
    if not (hs.top or hs.bottom or hs.center):
        return [], None
    if case.rimfire:
        cap = hs.size or case.base_dia * 0.42
        placed = [(hs.center, Matrix.Rotation(math.radians(rng.gauss(0, 3)), 4, "Z"), 0.0)]
        tools = [
            (_layer(placed, cap, 0.28, 0.0, 0.20, "_hs_outer"), "UNION"),  # rises 0.08
            (_layer(placed, cap, 0.34, -0.05 * cap, 0.20, "_hs_core"), "UNION"),  # rises 0.14
        ]
        return _nonempty(tools), (0.0, cap * 0.75, -0.16, 0.03)
    inner = case.primer_cup_dia / 2 + 0.35
    outer = case.rim_dia / 2 - case.rim_chamfer * case.rim_thickness - 0.30
    radius = (inner + outer) / 2
    cap = hs.size or min(1.25, (outer - inner) * 0.62)
    placed = []
    for text, top in ((hs.top, True), (hs.bottom, False)):
        if text:
            p, span = _arc_layout(text, radius, cap, top, rng)
            placed += p
            if span > 165:
                print(f"  warning: {cart.key} headstamp '{text}' spans {span:.0f} degrees; set headstamp.size smaller")
    tools = [
        (_layer(placed, cap, 0.30, 0.0, STAMP_DEPTH * 0.4, "_hs_outer"), "DIFFERENCE"),
        (_layer(placed, cap, 0.40, -0.035 * cap, STAMP_DEPTH, "_hs_core"), "DIFFERENCE"),
    ]
    return _nonempty(tools), (inner - 0.25, outer + 0.25, -0.01, STAMP_DEPTH + 0.05)


def _nonempty(tools):
    kept = []
    for me, op in tools:
        if len(me.vertices):
            kept.append((me, op))
        else:
            bpy.data.meshes.remove(me)
    return kept


def apply_boolean(obj: bpy.types.Object, tool_me: bpy.types.Mesh, operation: str) -> str:
    """Bake a boolean into obj's mesh. Tries the fast Manifold solver, falls back to Exact."""
    tool = bpy.data.objects.new("_tool", tool_me)
    bpy.context.scene.collection.objects.link(tool)
    before = len(obj.data.polygons)
    used = "failed"
    for solver in ("MANIFOLD", "EXACT"):
        mod = obj.modifiers.new("headstamp", "BOOLEAN")
        mod.operation = operation
        mod.object = tool
        mod.solver = solver
        if solver == "EXACT":
            mod.use_self = True
            mod.use_hole_tolerant = True
        dg = bpy.context.evaluated_depsgraph_get()
        new_me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
        obj.modifiers.remove(mod)
        if len(new_me.polygons) > before:
            old = obj.data
            new_me.name = old.name
            for i, m in enumerate(old.materials):
                if i >= len(new_me.materials):
                    new_me.materials.append(m)
            obj.data = new_me
            bpy.data.meshes.remove(old)
            used = solver
            break
        bpy.data.meshes.remove(new_me)
    bpy.data.objects.remove(tool)
    bpy.data.meshes.remove(tool_me)
    return used


def soften(me: bpy.types.Mesh, region, iterations: int = 5, factor: float = 0.5) -> None:
    """Relax vertices in the stamp region: real headstamps are rounded and imprecise."""
    r0, r1, z0, z1 = (v * MM for v in region)
    bm = bmesh.new()
    bm.from_mesh(me)
    sel = [v for v in bm.verts if z0 <= v.co.z <= z1 and r0 <= math.hypot(v.co.x, v.co.y) <= r1]
    for _ in range(iterations):
        bmesh.ops.smooth_vert(bm, verts=sel, factor=factor, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    for e in bm.edges:  # letter walls shade smoothly instead of as crisp machined edges
        if e.verts[0] in sel or e.verts[1] in sel:
            e.smooth = True
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(40))
    attr = me.attributes.get("sharp_edge")
    if attr is not None:  # keep letters soft even where the angle test marks them sharp
        rr = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", rr)
        rr = rr.reshape(-1, 3)
        inside = (rr[:, 2] >= z0) & (rr[:, 2] <= z1) & (np.hypot(rr[:, 0], rr[:, 1]) >= r0) & (np.hypot(rr[:, 0], rr[:, 1]) <= r1)
        ev = np.empty(len(me.edges) * 2, dtype=np.int32)
        me.edges.foreach_get("vertices", ev)
        ev = ev.reshape(-1, 2)
        sharp = np.empty(len(me.edges), dtype=bool)
        attr.data.foreach_get("value", sharp)
        sharp &= ~(inside[ev[:, 0]] | inside[ev[:, 1]])
        attr.data.foreach_set("value", sharp)


# ---------------------------------------------------------------- cavity attribute


def _arrays(me):
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    nor = np.empty(n * 3)
    me.vertex_normals.foreach_get("vector", nor)
    co, nor = co.reshape(-1, 3) / MM, nor.reshape(-1, 3)
    r = np.hypot(co[:, 0], co[:, 1])
    radial = (co[:, 0] * nor[:, 0] + co[:, 1] * nor[:, 1]) / np.maximum(r, 1e-6)
    return r, co[:, 2], radial, nor[:, 2]


def _store(me, values, name="cavity"):
    attr = me.attributes.get(name) or me.attributes.new(name, "FLOAT", "POINT")
    attr.data.foreach_set("value", values.astype(np.float32))


def case_cavity(me, case, region) -> None:
    """Bake vertex attributes for the shader.

    ``cavity``: where grime and shadow collect (stamp letters, primer gap, groove, inside).
    ``interior``: 1 on the inside walls and floor, where a fired case carries soot.
    ``zn``: height along the case, 0 at the head and 1 at the mouth (soot gradients).
    ``anneal``: the band on rifle necks and shoulders that shows annealing colour.
    """
    r, z, radial, nz = _arrays(me)
    floor = case.web if case.rimfire else case.pocket_depth + case.web
    inside = (z > floor - 0.2) & ((radial < -0.3) | ((nz > 0.5) & (z < case.length - 1.0) & (r < case.base_dia / 2 - 0.3)))
    _store(me, inside.astype(np.float32), "interior")
    _store(me, np.clip(z / case.length, 0.0, 1.0), "zn")
    if case.bottleneck:
        t = np.clip((z - (case.shoulder_start - 6.0)) / 4.5, 0.0, 1.0)
        _store(me, t * t * (3 - 2 * t), "anneal")
    cav = np.zeros(len(r))
    cav = np.where((radial < -0.5) & (z > case.pocket_depth + 0.1), 0.5, cav)  # inside the case
    if not case.rimfire:
        cup, pocket = case.primer_cup_dia / 2, case.primer_cup_dia / 2 + 0.02
        cav = np.where((r > cup - 0.08) & (r < pocket + 0.1) & (z < 0.35), 0.8, cav)
        if region:
            r0, r1, _, z1 = region
            cav = np.where((z > 0.015) & (z < z1) & (r > r0) & (r < r1), 1.0, cav)
    if case.groove_dia:
        g = case.groove_dia / 2
        cav = np.where((r > g - 0.3) & (r < g + 0.08) & (z > case.rim_thickness) & (z < case.groove_top), np.maximum(cav, 0.35), cav)
    _store(me, cav)


def bullet_cavity(me, bullet) -> None:
    r, z, radial, nz = _arrays(me)
    cav = np.zeros(len(r))
    if bullet.cannelure_z is not None:
        w = bullet.cannelure_width / 2
        cav = np.where((np.abs(z - bullet.cannelure_z) < w) & (r < bullet.dia / 2 - 0.03), 0.6, cav)
    _store(me, cav)
