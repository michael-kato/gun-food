"""Headstamp geometry check. Runs inside Blender (~20 s):

    blender --background --factory-startup --python tests/test_headstamps.py

For every cartridge and every maker that loads it:

* builds the headstamp's boolean tools for a few seeds and checks each is a clean solid:
  manifold, with no faces crossing (letters, symbols, dots or the primer crimp running into
  each other). A tool that crosses itself makes the boolean drop letters without an error;
* stamps one real case and checks every letter floor carries the ``cavity`` attribute. In
  brass the letters read only through it, so a floor without it is an invisible letter.
"""

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from cartridges import specs, variation  # noqa: E402
from cartridges.blender import mesh  # noqa: E402
from cartridges.blender import scene  # noqa: E402

SEEDS = 6


def dark_floors(cart, cp) -> int:
    """Letter-floor faces of a stamped case that miss the cavity attribute."""
    me, _ = scene.case_mesh(cart, cp, "_t")
    n = len(me.polygons)
    nor = np.empty(n * 3)
    me.polygons.foreach_get("normal", nor)
    cen = np.empty(n * 3)
    me.polygons.foreach_get("center", cen)
    nor, cen = nor.reshape(-1, 3), cen.reshape(-1, 3) / mesh.MM
    cav = np.empty(len(me.vertices))
    me.attributes["cavity"].data.foreach_get("value", cav)
    r = np.hypot(cen[:, 0], cen[:, 1])
    floor = (nor[:, 2] < -0.9) & (cen[:, 2] > 0.03) & (cen[:, 2] < 0.4) & (r > cart.case.primer_cup_dia / 2 + 0.1)
    bad = sum(1 for i in np.where(floor)[0] if cav[list(me.polygons[i].vertices)].mean() < 0.9)
    bpy.data.meshes.remove(me)
    return bad


def main():
    t0 = time.time()
    makers = specs.default_makers()
    fails, checked, stamped = [], 0, 0
    for cart in specs.load_all():
        for maker in makers.for_cartridge(cart):
            for seed in range(SEEDS):
                cp = variation.realize(cart, variation.copy_seed(seed, cart.key, maker), "case", maker=maker)
                tools, _ = mesh.headstamp_tools(cart, cp, random.Random(cp.headstamp_seed))
                if not tools:
                    fails.append(f"{cart.key} {maker} seed {seed}: no headstamp")
                for tool, _op in tools:
                    checked += 1
                    n = mesh.crossings(tool)
                    if n or not mesh._is_manifold(tool):
                        fails.append(f"{cart.key} {maker} seed {seed} {tool.name}: {n} crossing faces, manifold={mesh._is_manifold(tool)} ({cp.lot.headstamp_text})")
                    bpy.data.meshes.remove(tool)
                if seed == 0 and not cart.case.rimfire:
                    stamped += 1
                    bad = dark_floors(cart, cp)
                    if bad:
                        fails.append(f"{cart.key} {maker}: {bad} letter-floor faces without cavity ({cp.lot.headstamp_text})")
    for f in fails:
        print("FAIL", f)
    print(f"{checked} headstamp tools and {stamped} stamped cases checked in {time.time() - t0:.0f}s, {len(fails)} failed")
    sys.exit(1 if fails else 0)


main()
