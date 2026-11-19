"""Checks that run without Blender: specs load, profiles are valid, sampled copies stay in tolerance.

Runs under pytest, or directly: ``python tests/test_specs_and_profiles.py``.
"""

import math
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cartridges import profiles, specs, variation  # noqa: E402

CARTS = specs.load_all()
TOL = 1e-6
COPIES = 40  # sampled copies per cartridge and kind


def _close(a, b, tol=TOL):
    return abs(a - b) <= tol


def _segments_cross(p1, p2, p3, p4):
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    return (d1 * d2 < -1e-12) and (d3 * d4 < -1e-12)


def _assert_simple_loop(pts, what):
    n = len(pts)
    segs = [((pts[i][0], pts[i][1]), (pts[(i + 1) % n][0], pts[(i + 1) % n][1])) for i in range(n)]
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            assert not _segments_cross(*segs[i], *segs[j]), f"{what}: profile crosses itself at segments {i}, {j}"
    assert all(p[0] >= 0 for p in pts), f"{what}: negative radius"


def _copies(cart, kind):
    return [variation.realize(cart, variation.copy_seed(1, cart.key, kind, i), kind) for i in range(COPIES)]


def test_all_requested_cartridges_present():
    wanted = {"9mm", "223", "45ACP", "40CAL", "380ACP", "762x39", "308", "300blackout", "22LR"}
    assert wanted <= {c.key for c in CARTS}


def test_308_and_300blk_share_bullet_diameter_and_library():
    by = {c.key: c for c in CARTS}
    assert by["308"].bullet.dia == by["300blackout"].bullet.dia
    bullets = specs.load_bullets()
    assert {by["308"].bullet.key, by["300blackout"].bullet.key} <= set(bullets)


def test_nominal_case_profiles_match_specs():
    for cart in CARTS:
        pts = profiles.case_profile(cart.case)
        _assert_simple_loop(pts, cart.key)
        assert _close(max(p[1] for p in pts), cart.case.length), cart.key
        assert _close(2 * max(p[0] for p in pts), max(cart.case.rim_dia, cart.case.base_dia)), cart.key
        if cart.case.bottleneck:
            neck = [p for p in pts if cart.case.neck_start + cart.case.neck_radius < p[1] < cart.case.length]
            assert _close(2 * max(p[0] for p in neck), cart.case.mouth_dia), cart.key


def test_nominal_bullet_profiles_match_specs():
    for cart in CARTS:
        pts = profiles.bullet_profile(cart.bullet)
        _assert_simple_loop(pts, cart.key)
        assert _close(max(p[1] for p in pts), cart.bullet.length), cart.key
        assert _close(2 * max(p[0] for p in pts), cart.bullet.dia), cart.key


def test_round_tips_are_round():
    for b in specs.load_bullets().values():
        if b.tip != "round":
            continue
        r, rt = b.dia / 2, b.tip_dia / 2
        rho, (pr, pz), zc = profiles.ogive_round(r, rt, b.length - b.nose_length, b.nose_length)
        assert rho > r, b.key
        assert _close(math.hypot(pr, pz - zc), rt, 1e-9), b.key  # tangent point lies on the tip sphere
        pts = profiles.bullet_profile(b)
        apex = [p for p in pts if p[1] > b.length - rt * 0.2]
        assert all(p[0] < rt for p in apex), f"{b.key}: tip is not rounded off"


def test_copies_stay_inside_tolerance():
    for cart in CARTS:
        k = cart.case
        for cp in _copies(cart, "loaded"):
            c = cp.case
            assert k.length - cart.tol("length_tol") - TOL <= c.length <= k.length + TOL, cart.key
            assert k.rim_dia - cart.tol("rim_dia_tol") - TOL <= c.rim_dia <= k.rim_dia + TOL, cart.key
            assert k.rim_thickness - cart.tol("rim_thickness_tol") - TOL <= c.rim_thickness <= k.rim_thickness + TOL, cart.key
            for name in ("base_dia", "mouth_dia", "shoulder_dia"):
                if getattr(k, name) is not None:
                    assert getattr(k, name) - cart.tol("body_dia_tol") - TOL <= getattr(c, name) <= getattr(k, name) + TOL, (cart.key, name)
            b = cart.bullet
            assert b.dia - b.dia_tol - TOL <= cp.bullet.dia <= b.dia + TOL, cart.key
            assert cart.oal_min - TOL <= cp.oal <= cart.oal_max + TOL, (cart.key, cp.oal)
            assert 0.5 < cp.seat_depth < c.length - 2, (cart.key, cp.seat_depth)


def test_copies_are_seeded_and_differ():
    cart = CARTS[0]
    a = variation.realize(cart, 123)
    b = variation.realize(cart, 123)
    c = variation.realize(cart, 124)
    assert a.labels() == b.labels()
    assert a.labels() != c.labels()


def test_sampled_profiles_are_valid():
    for cart in CARTS:
        for kind in ("loaded", "case", "bullet"):
            for cp in _copies(cart, kind)[:10]:
                _assert_simple_loop(profiles.case_profile(cp.case, cp.crimp), f"{cart.key} {kind} case")
                _assert_simple_loop(profiles.bullet_profile(cp.bullet), f"{cart.key} {kind} bullet")


def test_crimp_narrows_the_mouth():
    for cart in CARTS:
        if cart.crimp == "none":
            continue
        crimp = profiles.Crimp(cart.crimp, cart.crimp_amount, cart.crimp_length)
        top = lambda pts: max(p[0] for p in pts if p[1] > cart.case.length - 0.2)  # noqa: E731
        assert top(profiles.case_profile(cart.case, crimp)) < top(profiles.case_profile(cart.case)) - cart.crimp_amount / 2 * 0.8, cart.key


def test_dents_push_inward_on_the_body_only():
    cart = CARTS[0]
    cp = variation.realize(cart, 5, "case")
    cp = replace(cp, case_dents=[variation.Dent(z=10.0, theta=0.0, radius=1.5, depth=0.05)], ovality=(0.0, 0.0))
    r = cart.case.base_dia / 2
    assert _close(variation.case_offset(cp, r, 10.0, 0.0), -0.05)
    assert variation.case_offset(cp, r, 10.0, math.pi) == 0.0
    assert variation.case_offset(cp, r, 0.5, 0.0) == 0.0  # head untouched


def test_bad_spec_is_rejected():
    bad = (specs.SPEC_DIR / "9mm.toml").read_text(encoding="utf-8").replace("oal = 29.21", "oal = 40.0")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.toml"
        p.write_text(bad, encoding="utf-8")
        try:
            specs.load(p)
        except specs.SpecError as e:
            assert "seat depth" in str(e) or "loaded length" in str(e)
        else:
            raise AssertionError("bad spec was accepted")


def test_specs_md_is_current():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import gen_specs_md

    current = gen_specs_md.OUT.read_text(encoding="utf-8")
    assert current == gen_specs_md.generate(), "SPECS.md is out of date: run python tools/gen_specs_md.py"


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
