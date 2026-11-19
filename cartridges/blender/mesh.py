"""Mesh construction in Blender: lathe-revolved parts and stamped headstamps."""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix

MM = 0.001  # Blender units are metres; specs are millimetres


def lathe(name: str, profile, segments: int = 96) -> bpy.types.Mesh:
    """Revolve a closed ``(r, z, mat)`` profile (mm) around Z into a watertight mesh (m)."""
    bm = bmesh.new()
    rings = []
    for r, z, _ in profile:
        if r < 1e-6:
            rings.append([bm.verts.new((0.0, 0.0, z * MM))])
        else:
            rings.append(
                [
                    bm.verts.new((r * MM * math.cos(2 * math.pi * k / segments), r * MM * math.sin(2 * math.pi * k / segments), z * MM))
                    for k in range(segments)
                ]
            )
    n = len(profile)
    for i in range(n):
        a, b, mat = rings[i], rings[(i + 1) % n], profile[i][2]
        if len(a) == 1 and len(b) == 1:
            continue
        for k in range(segments):
            k2 = (k + 1) % segments
            if len(a) == 1:
                verts = (a[0], b[k2], b[k])
            elif len(b) == 1:
                verts = (a[k], a[k2], b[0])
            else:
                verts = (a[k], a[k2], b[k2], b[k])
            bm.faces.new(verts).material_index = mat
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    finish_shading(me)
    return me


def finish_shading(me: bpy.types.Mesh, angle: float = 35.0) -> None:
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(angle))


def _glyph(ch: str, cap_height: float, depth: float) -> bpy.types.Mesh:
    cu = bpy.data.curves.new("_glyph", type="FONT")
    cu.body = ch
    cu.size = cap_height / 0.72  # font size is the em; capitals are ~72% of it
    cu.extrude = depth / 2
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    ob = bpy.data.objects.new("_glyph", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return me


def _arc_text(bm, text, radius, cap, depth, top: bool):
    glyphs = []
    for ch in text:
        if ch == " ":
            glyphs.append((None, 0.45 * cap))
            continue
        me = _glyph(ch, cap, depth)
        xs = [v.co.x for v in me.vertices] or [0.0]
        glyphs.append((me, max(max(xs) - min(xs), 0.3 * cap)))
    gap = 0.14 * cap
    total = sum(w for _, w in glyphs) + gap * (len(glyphs) - 1)
    span = total / radius
    s = 0.0
    for me, w in glyphs:
        centre = s + w / 2
        s += w + gap
        if me is None:
            continue
        if top:  # clockwise across the top, letters' bottoms toward the centre
            alpha = math.pi / 2 + span / 2 - centre / radius
            psi = alpha - math.pi / 2
        else:  # counter-clockwise across the bottom, upright
            alpha = -math.pi / 2 - span / 2 + centre / radius
            psi = alpha + math.pi / 2
        me.transform(Matrix.Translation((radius * math.cos(alpha), radius * math.sin(alpha), 0)) @ Matrix.Rotation(psi, 4, "Z"))
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    return math.degrees(span)


def headstamp_tool(cart) -> tuple[bpy.types.Mesh | None, str]:
    """Letters as a solid cutting tool, positioned on the case head (z = 0, facing -Z).

    Returns ``(mesh, boolean_operation)``. Centerfire marks are stamped in
    (DIFFERENCE); rimfire marks are raised (UNION).
    """
    hs, c = cart.headstamp, cart.case
    if not (hs.top or hs.bottom or hs.center):
        return None, ""
    bm = bmesh.new()
    if c.rimfire:
        cap = hs.size or c.base_dia * 0.42
        raise_h, inside = 0.10, 0.20
        depth = raise_h + inside
        _place_centre(bm, hs.center, cap, depth)
        z_shift = inside - depth / 2  # range [-raise_h, inside] after the flip
        op = "UNION"
    else:
        inner = c.primer_cup_dia / 2 + 0.35
        outer = c.rim_dia / 2 - 0.30 * c.rim_thickness - 0.30
        radius = (inner + outer) / 2
        cap = hs.size or min(1.25, (outer - inner) * 0.62)
        stamp, outside = 0.12, 0.25
        depth = stamp + outside
        for text, top in ((hs.top, True), (hs.bottom, False)):
            if text:
                span = _arc_text(bm, text, radius, cap, depth, top)
                if span > 165:
                    print(f"  warning: {cart.key} headstamp '{text}' spans {span:.0f} degrees; set headstamp.size smaller")
        z_shift = stamp - depth / 2  # range [-outside, stamp] after the flip
        op = "DIFFERENCE"
    # Built reading correctly from +Z; the head faces -Z, so turn it over (rotation, not a mirror)
    # and move it so it cuts into / rises from the head face. Then millimetres -> metres.
    xf = Matrix.Scale(MM, 4) @ Matrix.Translation((0, 0, z_shift)) @ Matrix.Rotation(math.pi, 4, "Y")
    bmesh.ops.transform(bm, matrix=xf, verts=bm.verts[:])
    # Font meshes come out with caps and side walls unwelded; weld them into closed solids.
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(f"{cart.key}_headstamp_tool")
    bm.to_mesh(me)
    bm.free()
    return me, op


def _place_centre(bm, text, cap, depth):
    me = _glyph(text, cap, depth)
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)


def apply_boolean(obj: bpy.types.Object, tool_me: bpy.types.Mesh, operation: str) -> str:
    """Bake a boolean into obj's mesh. Tries the fast Manifold solver, falls back to Exact."""
    tool = bpy.data.objects.new("_tool", tool_me)
    bpy.context.scene.collection.objects.link(tool)
    before = len(obj.data.polygons)
    used = ""
    for solver in ("MANIFOLD", "EXACT"):
        mod = obj.modifiers.new("headstamp", "BOOLEAN")
        mod.operation = operation
        mod.object = tool
        mod.solver = solver
        if solver == "EXACT":
            mod.use_self = True  # some glyphs have overlapping outlines
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
            finish_shading(new_me)
            used = solver
            break
        bpy.data.meshes.remove(new_me)
    bpy.data.objects.remove(tool)
    bpy.data.meshes.remove(tool_me)
    return used or "failed"
