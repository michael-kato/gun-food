"""Build the Blender extension ZIP: ``dist/gun_food-<version>.zip``.

The ZIP's root is the ``cartridges`` package (with ``blender_manifest.toml``), plus the spec
and bullet TOML files under ``data/`` and the LICENSE. Install it in Blender with
Edit > Preferences > Get Extensions > (menu) Install from Disk, or drag it into the window.

    python tools/package_addon.py            # build
    python tools/package_addon.py --check    # also run Blender's validator (needs blender on PATH or --blender)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "cartridges"
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def files():
    """(path in zip, source path) for everything the extension needs."""
    for src in sorted(PKG.rglob("*")):
        rel = src.relative_to(PKG)
        if src.is_file() and not SKIP_DIRS & set(rel.parts) and src.suffix not in SKIP_SUFFIXES and rel.parts[0] != "data":
            yield rel.as_posix(), src
    for folder in ("specs", "bullets"):
        for src in sorted((ROOT / folder).glob("*.toml")):
            yield f"data/{folder}/{src.name}", src
    yield "LICENSE", ROOT / "LICENSE"


def build(out_dir: Path) -> Path:
    manifest = tomllib.loads((PKG / "blender_manifest.toml").read_text(encoding="utf-8"))
    version = manifest["version"]
    init = (PKG / "__init__.py").read_text(encoding="utf-8")
    if f'__version__ = "{version}"' not in init:
        sys.exit(f"version mismatch: blender_manifest.toml says {version}, cartridges/__init__.py doesn't")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{manifest['id']}-{version}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in files():
            z.write(src, arc)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    ap.add_argument("--check", action="store_true", help="run `blender --command extension validate` on the ZIP")
    ap.add_argument("--blender", default=shutil.which("blender") or "blender")
    args = ap.parse_args()
    out = build(args.out)
    with zipfile.ZipFile(out) as z:
        n = len(z.namelist())
    print(f"wrote {out} ({n} files, {out.stat().st_size / 1024:.0f} KB)")
    if args.check:
        r = subprocess.run([args.blender, "--factory-startup", "--command", "extension", "validate", str(out)], timeout=120)
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
