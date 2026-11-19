"""Checks that run without Blender: specs load, profiles are valid and match the specs.

Runs under pytest, or directly: ``python tests/test_specs_and_profiles.py``.
"""

import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cartridges import profiles, specs  # noqa: E402

CARTS = specs.load_all()
TOL = 1e-6


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


def test_all_requested_cartridges_present():
    wanted = {"9mm", "223", "45ACP", "40CAL", "380ACP", "762x39", "308", "300blackout", "22LR"}
    assert wanted <= {c.key for c in CARTS}


def test_case_profiles_match_specs():
    for cart in CARTS:
        pts = profiles.case_profile(cart.case)
        _assert_simple_loop(pts, cart.key)
        assert _close(max(p[1] for p in pts), cart.case.length), cart.key
        assert _close(2 * max(p[0] for p in pts), max(cart.case.rim_dia, cart.case.base_dia)), cart.key
        if cart.case.bottleneck:
            # past the shoulder-to-neck fillet, the neck is exactly the neck diameter
            neck = [p for p in pts if cart.case.neck_start + cart.case.neck_radius < p[1] < cart.case.length]
            assert _close(2 * max(p[0] for p in neck), cart.case.mouth_dia), cart.key


def test_bullet_profiles_match_specs():
    for cart in CARTS:
        pts = profiles.bullet_profile(cart.bullet, cart.seat_depth)
        _assert_simple_loop(pts, cart.key)
        assert _close(max(p[1] for p in pts), cart.bullet.length), cart.key
        assert _close(2 * max(p[0] for p in pts), cart.bullet.dia), cart.key


def test_loaded_length_is_oal():
    for cart in CARTS:
        _, bullet, _, z = profiles.cartridge_profiles(cart)
        assert _close(z + max(p[1] for p in bullet), cart.oal), cart.key


def test_shoulder_angles():
    for cart in CARTS:
        k = cart.case
        if not k.bottleneck:
            continue
        half = math.degrees(math.atan((k.shoulder_dia - k.mouth_dia) / 2 / (k.neck_start - k.shoulder_start)))
        if k.shoulder_angle is not None:
            assert _close(half, k.shoulder_angle, 0.05), (cart.key, half)
        assert 10 < half < 40, (cart.key, half)


def test_bad_spec_is_rejected():
    bad = (specs.SPEC_DIR / "9mm.toml").read_text(encoding="utf-8").replace("oal = 29.69", "oal = 40.0")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.toml"
        p.write_text(bad, encoding="utf-8")
        try:
            specs.load(p)
        except specs.SpecError as e:
            assert "seat depth" in str(e)
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
