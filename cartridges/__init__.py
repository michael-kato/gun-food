"""Parametric, dimensionally accurate cartridge models for Blender.

This package is also the Blender extension (see ``blender_manifest.toml``): Blender calls
``register()`` / ``unregister()``. Everything that needs ``bpy`` is imported lazily, so the
spec, profile and variation modules stay usable from plain Python.
"""

__version__ = "0.2.0"


def register():
    from .blender import addon

    addon.register()


def unregister():
    from .blender import addon

    addon.unregister()
