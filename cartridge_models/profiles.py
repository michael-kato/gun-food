"""2D half-profiles for lathe-revolved parts. Pure Python, millimetres.

A profile is a list of ``(r, z, material_index)`` points. Revolved around the
z axis it forms a closed solid: the segment from point *i* to point *i + 1*
uses point *i*'s material index, and the last point joins back to the first.
Points with ``r == 0`` sit on the axis and become a single vertex.

The case head is at z = 0 and the case extends toward +z.
"""

from __future__ import annotations

import math

from .specs import BulletSpec, CaseSpec, Cartridge

CASE_METAL = 0
JACKET, CORE = 0, 1


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
        return [p]  # straight through: nothing to round
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


def case_profile(c: CaseSpec, seg: int = 5):
    R, t = c.rim_dia / 2, c.rim_thickness
    P1, H1, L = c.base_dia / 2, c.mouth_dia / 2, c.length
    mw = c.mouth_wall
    m = CASE_METAL

    if c.rimfire:
        head = c.web
        pts = [
            (0.0, 0.0, 0, m),
            (R, 0.0, 0.30, m),
            (R, t, 0.30, m),
            (P1, t, 0.20, m),
            (P1, L - 0.08, 0.0, m),
            (P1 - 0.08, L, 0.0, m),
            (P1 - mw + 0.05, L, 0.0, m),
            (P1 - mw, L - 0.08, 0.0, m),
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
    f = 0.30 * t  # rim chamfer
    pts = [
        (fh, pd, 0, m),
        (rp, pd, 0.25, m),
        (rp, 0.15, 0, m),
        (rp + 0.15, 0.0, 0, m),  # pocket mouth chamfer
        (R - f, 0.0, 0, m),
        (R, f, 0, m),
        (R, t, 0.06, m),
    ]
    if c.rimless:
        G, E = c.groove_dia / 2, c.groove_top
        rim_dz = (R - G) * math.tan(math.radians(c.rim_bevel_angle))
        front_dz = (P1 - G) / math.tan(math.radians(c.groove_front_angle))
        room = E - t - 0.25  # keep at least a 0.25 mm flat at the groove bottom
        if rim_dz + front_dz > room:
            k = room / (rim_dz + front_dz)
            rim_dz, front_dz = rim_dz * k, front_dz * k
        pts += [(G, t + rim_dz, 0.12, m), (G, E - front_dz, 0.20, m), (P1, E, 0.40, m)]
    else:
        pts += [(P1, t, 0.25, m)]
    if c.bottleneck:
        P2 = c.shoulder_dia / 2
        pts += [(P2, c.shoulder_start, c.shoulder_radius, m), (H1, c.neck_start, c.neck_radius, m)]
    pts += [
        (H1, L - 0.12, 0, m),
        (H1 - 0.10, L, 0, m),  # mouth chamfer, outside
        (H1 - mw + 0.06, L, 0, m),
        (H1 - mw, L - 0.10, 0, m),  # mouth chamfer, inside
    ]
    if c.bottleneck:
        sw = mw + 0.12
        pts += [(H1 - mw, c.neck_start + 0.20, 0.8, m), (P2 - sw, c.shoulder_start + 0.20, 0.8, m)]
    pts += [(P1 - c.base_wall, floor, 1.2, m), (fh, floor, 0, m)]
    return round_corners(pts, seg)


def _ogive(r, m, z0, length, seg):
    """Tangent ogive from radius r at z0 to meplat radius m at z0 + length."""
    a = r - m
    rho = (length**2 + a**2) / (2 * a)
    out = []
    for i in range(1, seg + 1):
        dz = length * math.sin(i / seg * math.pi / 2)  # denser toward the tip
        out.append(((r - rho) + math.sqrt(max(rho**2 - dz**2, 0.0)), z0 + dz))
    out[-1] = (m, z0 + length)
    return out


def bullet_profile(b: BulletSpec, seat_depth: float, seg: int = 32):
    r, L = b.dia / 2, b.length
    m = b.meplat_dia / 2
    J, C = JACKET, (CORE if b.exposed_base > 0 else JACKET)
    pts = []
    if b.heel_dia:
        hr = b.heel_dia / 2
        pts += [(0.0, 0.0, 0, J), (hr, 0.0, 0.25, J), (hr, seat_depth - 0.15, 0.10, J), (r, seat_depth + 0.10, 0.10, J)]
    elif b.boattail_length:
        btr = r - b.boattail_length * math.tan(math.radians(b.boattail_angle))
        er = btr * b.exposed_base
        if er > 0:
            pts += [(0.0, 0.0, 0, C), (er, 0.0, 0, J)]
        else:
            pts += [(0.0, 0.0, 0, J)]
        pts += [(btr, 0.0, 0.25, J), (r, b.boattail_length, 0.40, J)]
    else:
        er = r * b.exposed_base
        if er > 0:
            pts += [(0.0, 0.0, 0, C), (er, 0.0, 0, J)]
        else:
            pts += [(0.0, 0.0, 0, J)]
        pts += [(r, 0.0, min(0.5, r * 0.12), J)]
    if b.cannelure:
        w, d = b.cannelure_width, 0.10
        cz = seat_depth - 0.35  # the case mouth covers the lower part of the groove
        pts += [(r, cz - w / 2, 0.05, J), (r - d, cz - w / 2 + 0.12, 0, J), (r - d, cz + w / 2 - 0.12, 0, J), (r, cz + w / 2, 0.05, J)]
    z_nose = L - b.nose_length
    pts.append((r, z_nose, 0, J))
    ogive = _ogive(r, m, z_nose, b.nose_length, seg)
    for i, (orr, oz) in enumerate(ogive):
        last = i == len(ogive) - 1
        pts.append((orr, oz, (min(0.35, m * 0.5) if (last and m > 0) else 0), J))
    if m > 0:
        pts.append((0.0, L, 0, J))
    return round_corners(pts, seg=4)


def primer_profile(c: CaseSpec, recess: float = 0.08):
    """Primer cup, top face ``recess`` mm inside the case head."""
    rc = c.primer_cup_dia / 2
    pts = [(0.0, recess, 0, 0), (rc, recess, 0.25, 0), (rc, c.pocket_depth, 0, 0), (0.0, c.pocket_depth, 0, 0)]
    return round_corners(pts, seg=4)


def cartridge_profiles(cart: Cartridge):
    """Case, bullet and (centerfire) primer profiles plus the bullet's z offset when loaded."""
    case = case_profile(cart.case)
    bullet = bullet_profile(cart.bullet, cart.seat_depth)
    primer = None if cart.case.rimfire else primer_profile(cart.case)
    return case, bullet, primer, cart.case.length - cart.seat_depth
