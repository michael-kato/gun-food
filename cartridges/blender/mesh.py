"""Mesh construction in Blender: lathe-revolved parts, stamped headstamps, cavity attribute."""

from __future__ import annotations

import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix
from mathutils.bvhtree import BVHTree

MM = 0.001  # Blender units are metres; specs are millimetres

CASE_SEGMENTS = 64
BULLET_SEGMENTS = 48
PRIMER_SEGMENTS = 32
STAMP_DEPTH = 0.16  # mm, how deep headstamp letter cores are pressed in
MICRO_AMP = 0.008  # mm, micro relief on smooth surfaces (scaled per copy, see variation.Copy.micro)
MICRO_EDGE = 3.0  # times as much right at an edge (mouth, rim, bullet tip and base)
MICRO_FALLOFF = 0.8  # mm, how fast the edge boost fades


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


def micro_relief(me: bpy.types.Mesh, amount: float, seed: int, edges=(), waves: int = 16) -> None:
    """Press a few microns of smooth waviness into a lathed part, so reflections wobble a little
    instead of looking machined-perfect. Stronger within ~1 mm of the heights in ``edges``
    (mm), where real parts take their knocks.

    The relief only ever goes inward (radially), so measured diameters stay inside their
    tolerance bands; inner and outer walls move together, so wall thickness holds. Wavelengths
    stay above ~1.5 mm, which the lathe's vertex spacing can carry without aliasing.
    """
    if amount <= 0:
        return
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) / MM
    r = np.hypot(co[:, 0], co[:, 1])
    th = np.arctan2(co[:, 1], co[:, 0])
    z = co[:, 2]
    rng = np.random.default_rng(seed)
    m = rng.integers(2, 18, waves) * rng.choice((-1, 1), waves)  # whole waves around the part
    kz = 2 * np.pi / rng.uniform(1.5, 6.0, waves) * rng.choice((-1, 1), waves)
    ph = rng.uniform(0, 2 * np.pi, waves)
    a = rng.uniform(0.4, 1.0, waves)
    h = np.sin(np.outer(th, m) + np.outer(z, kz) + ph) @ a / np.sqrt((a * a).sum() / 2)
    h = 0.5 + 0.5 * np.tanh(0.8 * h)  # 0-1, pressed in
    boost = np.zeros(n)
    for e in edges:
        boost = np.maximum(boost, np.exp(-np.abs(z - e) / MICRO_FALLOFF))
    off = -MICRO_AMP * amount * (1 + (MICRO_EDGE - 1) * boost) * h
    off *= np.clip(r / 0.6, 0.0, 1.0)  # fade out toward the axis (bullet tips, head centre)
    scale = np.where(r > 1e-6, (r + off) / np.maximum(r, 1e-6), 1.0)
    co[:, 0] *= scale
    co[:, 1] *= scale
    me.vertices.foreach_set("co", (co * MM).ravel())
    me.update()


def finish_shading(me: bpy.types.Mesh, angle: float = 40.0) -> None:
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(angle))


# ---------------------------------------------------------------- headstamps
#
# A headstamp is a list of placed shapes: ``(shape, matrix, extra_depth)``. The matrix
# places the shape in the head's plane (mm, reading from +Z); a shape is a character or
# a tuple centred on the origin: ("annulus", r_in, r_out), ("disc", r) or
# ("plus", arm, half_width). Stroke offsets grow (+) or thin (-) every kind alike.

# symbols, in units of the letter height
SYMBOL_SHAPES = {
    "nato": (("annulus", 0.40, 0.55), ("plus", 0.27, 0.075)),  # circled cross
    "ring": (("annulus", 0.36, 0.50), ("disc", 0.13)),  # a maker's roundel
    "dot": (("disc", 0.16),),
}


def _glyph(ch: str, cap: float, depth: float, offset: float = 0.0) -> bpy.types.Mesh:
    """Extruded text, centred on its advance box. ``offset`` grows (+) or thins (-) the strokes."""
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


def _circle(r, n):
    return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def _shape_mesh(shape, cap: float, depth: float, offset: float) -> bpy.types.Mesh | None:
    """Mesh for one shape, extruded to +-depth/2 (None if the offset thins it away)."""
    if isinstance(shape, str):
        return _glyph(shape, cap, depth, offset)
    kind, h = shape[0], depth / 2
    verts, faces = [], []

    def loop(pts, z):
        start = len(verts)
        verts.extend((x, y, z) for x, y in pts)
        return list(range(start, start + len(pts)))

    if kind == "annulus":
        ri, ro = shape[1] - offset, shape[2] + offset
        if ri < 0.02 or ro - ri < 0.03:
            return None
        n = max(24, int(ro * 24))
        ot, ob, it, ib = loop(_circle(ro, n), h), loop(_circle(ro, n), -h), loop(_circle(ri, n), h), loop(_circle(ri, n), -h)
        for k in range(n):
            k2 = (k + 1) % n
            faces += [(ot[k], ot[k2], it[k2], it[k]), (ob[k2], ob[k], ib[k], ib[k2]), (ob[k], ob[k2], ot[k2], ot[k]), (it[k], it[k2], ib[k2], ib[k])]
    else:
        if kind == "disc":
            r = shape[1] + offset
            if r < 0.03:
                return None
            pts = _circle(r, 20)
        else:  # plus
            a, w = shape[1] + offset, shape[2] + offset
            if w < 0.015 or a <= w:
                return None
            pts = [(w, -w), (a, -w), (a, w), (w, w), (w, a), (-w, a), (-w, w), (-a, w), (-a, -w), (-w, -w), (-w, -a), (w, -a)]
        top, bot = loop(pts, h), loop(pts, -h)
        n = len(pts)
        faces += [top, bot[::-1]]
        faces += [(bot[k], bot[(k + 1) % n], top[(k + 1) % n], top[k]) for k in range(n)]
    me = bpy.data.meshes.new("_shape")
    me.from_pydata(verts, [], faces)
    me.update()
    return me


EXTRA_DEPTH = 0.035  # mm, most a mark is struck deeper or shallower than the rest


def _extra(rng: random.Random) -> float:
    return max(-EXTRA_DEPTH, min(EXTRA_DEPTH, rng.gauss(0, 0.015)))


def _clock(at: float) -> float:
    """Angle (radians, from +X) of a clock position on the head, 12 o'clock = +Y."""
    return math.radians(90.0 - 30.0 * at)


def _arc_layout(text, radius, cap, at, rng: random.Random, width=1.0, grow=0.0, max_span=150.0):
    """Characters of ``text`` along an arc centred at clock position ``at``.

    Returns ``([(char, matrix_mm, extra_depth)], span_radians)``. Text in the top half reads
    clockwise with letter bottoms toward the centre; in the bottom half it reads
    counter-clockwise, upright. Text too long for ``max_span`` degrees is scaled down.
    Letters are spaced at their inner edge, where neighbours on a small arc crowd closest
    (overlapping letters break the boolean); ``grow`` is the bold outline's growth per side.
    """
    widths = []
    for ch in text:
        if ch == " ":
            widths.append(0.45 * cap * width)
            continue
        me = _glyph(ch, cap, 0.1)
        xs = [v.co.x for v in me.vertices] or [0.0]
        widths.append(max(max(xs) - min(xs), 0.3 * cap) * width + 2 * grow)
        bpy.data.meshes.remove(me)
    gap = 0.16 * cap * width
    total = sum(widths) + gap * (len(widths) - 1)
    r_in = max(radius - 0.55 * cap, 0.5 * radius)
    k = min(1.0, math.radians(max_span) * r_in / max(total, 1e-6))
    widths, gap, total = [w * k for w in widths], gap * k, total * k
    span = total / r_in
    phi = _clock(at)
    top = math.sin(phi) > -1e-6
    placed, s = [], 0.0
    for ch, w in zip(text, widths):
        centre = s + w / 2 + rng.gauss(0, 0.025)  # hand-set type: letters wander a little
        s += w + gap
        if ch == " ":
            continue
        rad = radius + rng.gauss(0, 0.035)
        if top:
            alpha = phi + span / 2 - centre / r_in
            psi = alpha - math.pi / 2
        else:
            alpha = phi - span / 2 + centre / r_in
            psi = alpha + math.pi / 2
        psi += math.radians(rng.gauss(0, 2.0))
        sc = k * (1 + rng.gauss(0, 0.04))
        m = Matrix.Translation((rad * math.cos(alpha), rad * math.sin(alpha), 0)) @ Matrix.Rotation(psi, 4, "Z") @ Matrix.Diagonal((sc * width, sc, 1.0, 1.0))
        placed.append((ch, m, _extra(rng)))  # some letters struck deeper than others
    return placed, span


def _symbol(name, radius, cap, phi, rng: random.Random):
    m = (
        Matrix.Translation((radius * math.cos(phi), radius * math.sin(phi), 0))
        @ Matrix.Rotation(phi - math.pi / 2 + math.radians(rng.gauss(0, 3)), 4, "Z")
        @ Matrix.Scale(1 + rng.gauss(0, 0.04), 4)
    )
    extra = _extra(rng)
    return [((s[0], *(v * cap for v in s[1:])), m, extra) for s in SYMBOL_SHAPES[name]]


def _is_manifold(me) -> bool:
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-7)
    ok = len(bm.edges) > 0 and all(e.is_manifold for e in bm.edges)
    bm.free()
    return ok


def crossings(me) -> int:
    """Pairs of faces that intersect without sharing a vertex (0 for a clean solid)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-7)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    hits = sum(1 for a, b in tree.overlap(tree) if a < b and not ({v.index for v in bm.faces[a].verts} & {v.index for v in bm.faces[b].verts}))
    bm.free()
    return hits


def _volume(me) -> float:
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    v = bm.calc_volume(signed=True)
    bm.free()
    return v


_plain_volume: dict = {}


def _offset_glyph(ch, cap, depth, offset):
    """``ch`` with its outline grown/thinned by ``offset``, or its plain outline when the
    offset one isn't a clean solid. Offset font outlines fold over themselves at tight
    corners (2, 3, 8, G, M, R, S, ...) and a folded tool silently eats or refills letters
    in the boolean, so each is checked: closed, no crossing faces, and a volume that grew
    or shrank the way the offset says."""
    if not offset:
        return _glyph(ch, cap, depth)
    key = (ch, round(cap, 4), round(depth, 4))
    if key not in _plain_volume:
        plain = _glyph(ch, cap, depth)
        _plain_volume[key] = _volume(plain)
        bpy.data.meshes.remove(plain)
    me = _glyph(ch, cap, depth, offset)
    v, v0 = _volume(me), _plain_volume[key]
    grew_right = (v > v0 * 1.02) if offset > 0 else (0.15 * v0 < v < v0 * 0.98)
    if grew_right and _is_manifold(me) and crossings(me) == 0:
        return me
    bpy.data.meshes.remove(me)
    return _glyph(ch, cap, depth)


def _layer(placed, cap, depth, offset, inside, name):
    """Build one cutting/raising layer from placed shapes.

    The layer spans ``depth`` mm through the head face, ``inside`` of it on the case side.
    """
    bm = bmesh.new()
    for shape, m, extra in placed:
        d = depth + 2 * abs(extra)
        me = _offset_glyph(shape, cap, d, offset) if isinstance(shape, str) else _shape_mesh(shape, cap, d, offset)
        if me is None:
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


def _free_angle(phi, taken, step=math.radians(12), tries=8):
    """``phi`` or the nearest angle (in ``step``s) outside every ``(centre, half_width)`` in ``taken``."""
    for i in range(tries):
        for cand in ((phi,) if i == 0 else (phi + i * step, phi - i * step)):
            if all(abs((cand - c + math.pi) % (2 * math.pi) - math.pi) > hw for c, hw in taken):
                return cand
    return None


def headstamp_tools(cart, cp, rng: random.Random):
    """Headstamp as boolean tools: ``([(mesh, operation), ...], region)``.

    The marks, symbols, dots and primer crimp come from the copy's maker (``cp.lot``).
    Real headstamps are pressed by a worn bunter: bold letters with rounded walls and soft
    bottoms. Each mark is made of two layers, a shallow full-width letter and a deeper,
    thinner core, which gives a sloped wall without the slow solver that bevelled text
    would need. ``region`` is the (r0, r1, z0, z1) box in mm around the stamp.
    Centerfire marks are pressed in (DIFFERENCE); rimfire marks are raised (UNION).
    """
    case, lot, hs = cp.case, cp.lot, cart.headstamp
    if lot is None or not lot.marks:
        return [], None
    st = lot.style
    if case.rimfire:
        text = next((v for k, v, _ in lot.marks if k == "text"), "")
        if not text:
            return [], None
        cap = (hs.size or case.base_dia * 0.42) * st.size
        placed = [(text, Matrix.Rotation(math.radians(rng.gauss(0, 3)), 4, "Z") @ Matrix.Diagonal((st.width, 1.0, 1.0, 1.0)), 0.0)]
        tools = [
            (_layer(placed, cap, 0.34, st.weight * cap, 0.20, "_hs_outer"), "UNION"),  # rises 0.14
            (_layer(placed, cap, 0.42, (st.weight - 0.03) * cap, 0.20, "_hs_core"), "UNION"),  # rises 0.22
        ]
        return _nonempty(tools), (0.0, cap * 0.75, -0.16, 0.03)

    pocket = case.primer_cup_dia / 2 + 0.02
    crimp = lot.primer_crimp
    inner = pocket + {"ring": 0.62, "stakes": 0.72}.get(crimp, 0.35)
    outer = case.rim_dia / 2 - case.head_chamfer - 0.30
    radius = (inner + outer) / 2
    cap = (hs.size or min(1.6, (outer - inner) * 0.72)) * st.size
    placed, taken = [], []
    for kind, value, at in lot.marks:
        phi = _clock(at or 12)
        if kind == "text":
            p, span = _arc_layout(value, radius, cap, at or 12, rng, st.width, max(st.weight, 0.0) * cap)
            placed += p
            taken.append((phi, span / 2 + 0.6 * cap / radius))
        else:
            placed += _symbol(value, radius, cap, phi, rng)
            taken.append((phi, 0.9 * cap / radius))
    for at in lot.dots:  # lot marks squeeze in wherever there's room
        phi = _free_angle(_clock(at), taken)
        if phi is not None:
            placed += _symbol("dot", radius, cap, phi, rng)
            taken.append((phi, 0.4 * cap / radius))
    if crimp == "ring":  # military primers are staked in with a ring around the pocket
        placed.append((("annulus", pocket + 0.12, pocket + 0.42), Matrix.Identity(4), abs(rng.gauss(0.0, 0.01))))
    elif crimp == "stakes":  # or with three stab marks
        a0 = rng.uniform(0, 2 * math.pi)
        for i in range(3):
            a = a0 + i * 2 * math.pi / 3 + math.radians(rng.gauss(0, 3))
            m = Matrix.Translation(((pocket + 0.40) * math.cos(a), (pocket + 0.40) * math.sin(a), 0)) @ Matrix.Rotation(a, 4, "Z") @ Matrix.Diagonal((1.0, 0.55, 1.0, 1.0))
            placed.append((("disc", 0.30), m, rng.gauss(0.0, 0.01)))
    depth = STAMP_DEPTH * st.depth
    tools = [
        (_layer(placed, cap, 0.30, st.weight * cap, depth * 0.55, "_hs_outer"), "DIFFERENCE"),
        (_layer(placed, cap, 0.40, (st.weight - 0.025) * cap, depth, "_hs_core"), "DIFFERENCE"),
    ]
    r0 = pocket + 0.05 if crimp != "none" else inner - 0.25
    return _nonempty(tools), (r0, outer + 0.25, -0.01, depth + 2 * EXTRA_DEPTH + 0.03)


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


def flatten_head(me, depth: float) -> None:
    """Flat-shade the faces that look out of the head (the face, letter floors, raised tops).

    The boolean leaves long sliver triangles across the head; smooth-shaded, their
    interpolated normals streak out from every letter and can wash whole letters out.
    Letter walls stay smooth so the strokes still read as soft.
    """
    n = len(me.polygons)
    nor = np.empty(n * 3)
    me.polygons.foreach_get("normal", nor)
    cen = np.empty(n * 3)
    me.polygons.foreach_get("center", cen)
    nz, z = nor.reshape(-1, 3)[:, 2], cen.reshape(-1, 3)[:, 2] / MM
    flat = (nz < -0.98) & (z > -0.4) & (z < depth + 0.1)
    attr = me.attributes.get("sharp_face") or me.attributes.new("sharp_face", "BOOLEAN", "FACE")
    cur = np.empty(n, dtype=bool)
    attr.data.foreach_get("value", cur)
    attr.data.foreach_set("value", cur | flat)


def primer_attrs(me, case) -> None:
    """``rn``: radius over the cup radius, so the shader can find the sealant ring at the rim."""
    r, _, _, _ = _arrays(me)
    _store(me, np.clip(r / (case.primer_cup_dia / 2), 0.0, 1.0), "rn")


def paint_tip(me, bullet, length: float, slot: int) -> None:
    """Put material ``slot`` on the jacket faces within ``length`` mm of the bullet's tip."""
    n = len(me.polygons)
    centres = np.empty(n * 3)
    me.polygons.foreach_get("center", centres)
    z = centres.reshape(-1, 3)[:, 2] / MM
    mats = np.empty(n, dtype=np.int32)
    me.polygons.foreach_get("material_index", mats)
    mats = np.where((z > bullet.length - length) & (mats == 0), slot, mats).astype(np.int32)
    me.polygons.foreach_set("material_index", mats)


def bullet_cavity(me, bullet) -> None:
    r, z, radial, nz = _arrays(me)
    cav = np.zeros(len(r))
    if bullet.cannelure_z is not None:
        w = bullet.cannelure_width / 2
        cav = np.where((np.abs(z - bullet.cannelure_z) < w) & (r < bullet.dia / 2 - 0.03), 0.6, cav)
    _store(me, cav)
