"""2D half-profiles for lathe-revolved parts. Pure Python, millimetres.

A profile is a list of ``(r, z, material_index)`` points. Revolved around the z axis
it forms a closed solid: the segment from point *i* to point *i + 1* uses point *i*'s
material index, and the last point joins back to the first. Points with ``r == 0`` sit
on the axis and become a single vertex.

The case head is at z = 0 and the case extends toward +z. Bullets start at their base.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .specs import BulletSpec, CaseSpec

CASE_METAL = 0
JACKET, CORE = 0, 1


@dataclass(frozen=True)
class Crimp:
    kind: str  # "taper" or "roll"
    amount: float  # reduction of the mouth's outside diameter, mm
    length: float  # length over which the case is drawn in, mm


# ---------------------------------------------------------------- helpers


def _fillet_arc(a, p, b, radius, seg):
    """Points of an arc rounding the corner at p between a-p and p-b."""
    ax, az = a[0] - p[0], a[1] - p[1]
    bx, bz = b[0] - p[0], b[1] - p[1]
    la, lb = math.hypot(ax, az), math.hypot(bx, bz)
    if radius <= 0 or la < 1e-9 or lb < 1e-9:
        return [p]
    ax, az, bx, bz = ax / la, az / la, bx / lb, bz / lb
    theta = math.acos(max(-1.0, min(1.0, ax * bx + az * bz)))
    if theta < 1e-3 or theta > math.pi - 1e-3:
        return [p]
    t = min(radius / math.tan(theta / 2), 0.45 * la, 0.45 * lb)
    r = t * math.tan(theta / 2)
    t1 = (p[0] + ax * t, p[1] + az * t)
    t2 = (p[0] + bx * t, p[1] + bz * t)
    mx, mz = ax + bx, az + bz
    lm = math.hypot(mx, mz)
    d = r / math.sin(theta / 2)
    c = (p[0] + mx / lm * d, p[1] + mz / lm * d)
    a1 = math.atan2(t1[1] - c[1], t1[0] - c[0])
    a2 = math.atan2(t2[1] - c[1], t2[0] - c[0])
    da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
    seg = max(1, min(seg, math.ceil(abs(da) * r / 0.15)))  # about one point per 0.15 mm of arc
    return [(c[0] + r * math.cos(a1 + da * i / seg), c[1] + r * math.sin(a1 + da * i / seg)) for i in range(seg + 1)]


def round_corners(points, seg: int = 5):
    """``points``: ``(r, z, fillet_radius, mat)``, a closed loop. Returns ``(r, z, mat)``."""
    n = len(points)
    out = []
    for i, (r, z, f, mat) in enumerate(points):
        prev, nxt = points[i - 1], points[(i + 1) % n]
        arc = _fillet_arc((prev[0], prev[1]), (r, z), (nxt[0], nxt[1]), f, seg) if f > 0 else [(r, z)]
        for j, (ar, az) in enumerate(arc):
            out.append((max(ar, 0.0), az, mat if j == len(arc) - 1 else prev[3]))
    deduped = []
    for q in out:
        if deduped and abs(q[0] - deduped[-1][0]) < 1e-7 and abs(q[1] - deduped[-1][1]) < 1e-7:
            deduped[-1] = q
            continue
        deduped.append(q)
    if len(deduped) > 1 and abs(deduped[0][0] - deduped[-1][0]) < 1e-7 and abs(deduped[0][1] - deduped[-1][1]) < 1e-7:
        deduped.pop()
    return deduped


def refine(profile, max_len: float, outside_only: bool = False):
    """Split segments longer than ``max_len`` so surface detail (dents) has vertices to move.

    Profiles run counter-clockwise, so outer surfaces are the segments that climb in z;
    ``outside_only`` refines just those and leaves hidden inner walls coarse.
    """
    out = []
    n = len(profile)
    for i, (r, z, m) in enumerate(profile):
        out.append((r, z, m))
        r2, z2, _ = profile[(i + 1) % n]
        if r < 1e-6 and r2 < 1e-6:
            continue  # along the axis
        if outside_only and z2 <= z:
            continue
        steps = int(math.hypot(r2 - r, z2 - z) / max_len)
        for k in range(1, steps + 1):
            t = k / (steps + 1)
            out.append((r + (r2 - r) * t, z + (z2 - z) * t, m))
    return out


# ---------------------------------------------------------------- case


def case_profile(c: CaseSpec, crimp: Crimp | None = None, seg: int = 5):
    R, t = c.rim_dia / 2, c.rim_thickness
    P1, H1, L = c.base_dia / 2, c.mouth_dia / 2, c.length
    mw = c.mouth_wall
    m = CASE_METAL
    d = crimp.amount / 2 if crimp else 0.0
    lc = crimp.length if crimp else 0.0

    if c.rimfire:
        head = c.web
        pts = [
            (0.0, 0.0, 0, m),
            (R, 0.0, 0.18, m),
            (R, t, 0.18, m),
            (P1, t, 0.15, m),
        ]
        if crimp:
            pts += [(P1, L - lc, 0.25, m)]
        pts += [
            (P1 - d, L - 0.08, 0, m),
            (P1 - d - 0.08, L, 0, m),
            (P1 - d - mw + 0.05, L, 0, m),
            (P1 - d - mw, L - 0.08, 0, m),
        ]
        if crimp:
            pts += [(P1 - mw, L - lc, 0.25, m)]
        pts += [
            (P1 - mw, t + 0.10, 0.15, m),  # inner wall down into the folded rim
            (R - 0.30, t - 0.25, 0.15, m),
            (R - 0.30, head, 0.10, m),
            (0.0, head, 0, m),
        ]
        return round_corners(pts, seg)

    rp = c.primer_cup_dia / 2 + 0.02  # pocket, a hair wider than the cup
    pd = c.pocket_depth
    fh = c.flash_hole_dia / 2
    floor = pd + c.web
    hc = min(c.head_chamfer, 0.3 * t)
    pts = [
        (fh, pd, 0, m),
        (rp, pd, 0.25, m),
        (rp, 0.15, 0.03, m),
        (rp + 0.15, 0.0, 0.03, m),  # pocket mouth chamfer
        (R - hc, 0.0, 0.03, m),  # head-side edge of the rim, just broken
        (R, hc, 0.03, m),
    ]
    if c.rimless:
        # SAAMI / C.I.P.: the rim's outer face, a bevel (f long, alpha from the axis) into the
        # rim's flat front face at the rim thickness, the groove bottom, the ramp (beta) to the body
        G, E = c.groove_dia / 2, c.groove_top
        f = min(c.rim_bevel, t - hc - 0.05)
        inset = min(f * math.tan(math.radians(c.rim_bevel_angle)), R - G)
        pts += [(R, t - f, 0.04, m)]
        if R - inset - G > 0.03:
            pts += [(R - inset, t, 0.04, m), (G, t, 0.08, m)]
        else:  # the bevel runs all the way down to the groove
            pts += [(G, t, 0.08, m)]
        front_dz = min((P1 - G) / math.tan(math.radians(c.groove_front_angle)), E - t - 0.25)
        pts += [(G, E - front_dz, 0.15, m), (P1, E, 0.30, m)]
    else:
        pts += [(R, t, 0.10, m), (P1, t, 0.30, m)]
    if c.bottleneck:
        P2 = c.shoulder_dia / 2
        pts += [(P2, c.shoulder_start, c.shoulder_radius, m), (H1, c.neck_start, c.neck_radius, m)]
    if crimp:  # a taper crimp closes the mouth gradually over its length, like the die's long taper
        pts += [(H1, L - lc, 1.5 if crimp.kind == "taper" else 0.30, m)]
    pts += [
        (H1 - d, L - 0.10, 0, m),
        (H1 - d - 0.04, L, 0, m),  # mouth chamfer, outside: barely broken on factory brass
        (H1 - d - mw + 0.06, L, 0, m),
        (H1 - d - mw, L - 0.10, 0, m),  # mouth chamfer, inside
    ]
    if crimp:
        pts += [(H1 - mw, L - lc, 0.30, m)]
    if c.bottleneck:
        sw = mw + 0.12
        pts += [(H1 - mw, c.neck_start + 0.20, 0.8, m), (P2 - sw, c.shoulder_start + 0.20, 0.8, m)]
    pts += [(P1 - c.base_wall, floor, 1.2, m), (fh, floor, 0, m)]
    return round_corners(pts, seg)


# ---------------------------------------------------------------- bullet


def _ogive_flat(r, m, z0, length, seg):
    """Tangent ogive from radius r at z0 to a flat meplat of radius m at z0 + length."""
    a = r - m
    rho = (length**2 + a**2) / (2 * a)
    out = []
    for i in range(1, seg + 1):
        dz = length * math.sin(i / seg * math.pi / 2)
        out.append(((r - rho) + math.sqrt(max(rho**2 - dz**2, 0.0)), z0 + dz))
    out[-1] = (m, z0 + length)
    return out


def nose_elliptic(r, z0, length, power, seg):
    """Pistol round nose: a superellipse quarter from radius r at z0 to the tip on the axis.

    Tangent to the bearing surface, and its curvature grows gradually up to a blunt, smooth tip
    (radius of curvature r**2 / length for an ellipse), where a tangent ogive into a small tip
    sphere looks pointed. ``power`` 2 is an ellipse; higher is fuller, lower more pointed.
    """
    e = 2.0 / power
    out = []
    for i in range(1, seg + 1):
        t = math.pi / 2 * i / seg
        out.append((r * math.cos(t) ** e, z0 + length * math.sin(t) ** e))
    out[-1] = (0.0, z0 + length)
    return out


def ogive_round(r, rt, z0, length):
    """Tangent ogive capped by a sphere of radius ``rt``, total nose length ``length``.

    Returns ``(rho, tangent_point, tip_centre_z)``: the ogive radius, where the ogive
    meets the tip sphere, and the sphere's centre height.
    """
    rho = ((length - rt) ** 2 + r**2 - rt**2) / (2 * (r - rt))
    zc = z0 + length - rt
    co = (r - rho, z0)  # ogive centre
    k = rho / (rho - rt)
    tangent = (co[0] + (0.0 - co[0]) * k, co[1] + (zc - co[1]) * k)
    return rho, tangent, zc


def _ogive_round_points(r, rt, z0, length, seg):
    rho, (pr, pz), zc = ogive_round(r, rt, z0, length)
    a1 = math.atan2(pz - z0, pr - (r - rho))
    out = []
    n1 = max(4, int(seg * 0.75))
    for i in range(1, n1 + 1):
        a = a1 * math.sin(i / n1 * math.pi / 2)
        out.append((r - rho + rho * math.cos(a), z0 + rho * math.sin(a)))
    b0 = math.atan2(pz - zc, pr)
    n2 = max(4, seg - n1)
    for i in range(1, n2 + 1):
        b = b0 + (math.pi / 2 - b0) * i / n2
        out.append((rt * math.cos(b), zc + rt * math.sin(b)))
    out[-1] = (0.0, z0 + length)
    return out


def bullet_profile(b: BulletSpec, seat_depth: float | None = None, seg: int = 32):
    r, L = b.dia / 2, b.length
    J, C = JACKET, (CORE if b.exposed_base > 0 else JACKET)
    pts = []
    if b.heel_dia:
        hr = b.heel_dia / 2
        hl = b.heel_length
        pts += [(0.0, 0.0, 0, J), (hr, 0.0, 0.25, J), (hr, hl - 0.15, 0.10, J), (r, hl + 0.10, 0.10, J)]
    elif b.boattail_length:
        btr = r - b.boattail_length * math.tan(math.radians(b.boattail_angle))
        er = btr * b.exposed_base
        pts += [(0.0, 0.0, 0, C), (er, 0.0, 0, J)] if er > 0 else [(0.0, 0.0, 0, J)]
        pts += [(btr, 0.0, 0.25, J), (r, b.boattail_length, 0.40, J)]
    else:
        er = r * b.exposed_base
        pts += [(0.0, 0.0, 0, C), (er, 0.0, 0, J)] if er > 0 else [(0.0, 0.0, 0, J)]
        pts += [(r, 0.0, min(0.5, r * 0.12), J)]
    if b.cannelure_z is not None:
        w, d = b.cannelure_width, 0.10
        cz = b.cannelure_z
        pts += [(r, cz - w / 2, 0.05, J), (r - d, cz - w / 2 + 0.12, 0, J), (r - d, cz + w / 2 - 0.12, 0, J), (r, cz + w / 2, 0.05, J)]
    z_nose = L - b.nose_length
    pts.append((r, z_nose, 0, J))
    if b.tip == "elliptic":
        for pr, pz in nose_elliptic(r, z_nose, b.nose_length, b.nose_power, seg):
            pts.append((pr, pz, 0, J))
    elif b.tip == "round":
        for pr, pz in _ogive_round_points(r, b.tip_dia / 2, z_nose, b.nose_length, seg):
            pts.append((pr, pz, 0, J))
    else:
        m = b.tip_dia / 2
        edge = min(1.6, m * 0.5)  # a well rounded meplat edge
        *ogive, corner = _ogive_flat(r, m, z_nose, b.nose_length, seg)
        # the ogive's points crowd the meplat, and a rounding can't be wider than about half
        # the segments beside it (see _fillet_arc): clear just enough of them out of its way
        far = next(q for q in reversed(ogive) if math.hypot(q[0] - corner[0], q[1] - corner[1]) > 0.3)
        theta = math.acos((corner[0] - far[0]) / math.hypot(far[0] - corner[0], far[1] - corner[1]))
        room = edge / math.tan(theta / 2) / 0.45
        for orr, oz in ogive:
            if math.hypot(orr - corner[0], oz - corner[1]) > room:
                pts.append((orr, oz, 0, J))
        pts.append((corner[0], corner[1], edge, J))
        pts.append((0.0, L, 0, J))
    return round_corners(pts, seg=8)


def primer_profile(c: CaseSpec, recess: float = 0.08, strike: tuple[float, float] | None = None):
    """Primer cup, top face ``recess`` mm inside the case head.

    ``strike`` = (radius, depth) adds a firing-pin crater in the middle of a fired primer.
    """
    rc = c.primer_cup_dia / 2
    if strike:
        sr, sd = min(strike[0], rc * 0.6), min(strike[1], c.pocket_depth * 0.4)
        rs = (sr**2 + sd**2) / (2 * sd)  # spherical crater, like a hemispherical firing pin
        pts = [(sr * i / 6, recess + math.sqrt(rs**2 - (sr * i / 6) ** 2) - (rs - sd), 0, 0) for i in range(6)]
        pts.append((sr, recess, 0.2, 0))
    else:
        pts = [(0.0, recess, 0, 0)]
    pts += [(rc, recess, 0.25, 0), (rc, c.pocket_depth, 0, 0), (0.0, c.pocket_depth, 0, 0)]
    return round_corners(pts, seg=4)
