"""Procedural, physically based metal materials (Cycles / EEVEE).

All metals share one node graph with different parameters:

* base colour = measured normal-incidence reflectance (linear RGB), edge tint = F82 tint
* large soft blotches of tarnish: darker colour, a little rougher, plus a thin oxide film
  (Principled thin film) that adds the faint iridescence real brass picks up
* fine roughness noise, drawing marks running along the part's axis, and sparse tiny dings
* brass only: an annealing stain on rifle necks and shoulders, driven by object properties
  ``anneal_z0`` / ``anneal_z1`` (mm from the head) and ``anneal_amt`` (0-1)

Texture space is object space in millimetres, and every pattern is offset by the object's
random value, so each instance of a shared mesh gets its own imperfections.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import bpy


@dataclass(frozen=True)
class Metal:
    base: tuple[float, float, float]
    edge: tuple[float, float, float]
    roughness: float
    roughness_var: float = 0.03
    tarnish: tuple[float, float, float] = (0.5, 0.4, 0.3)
    tarnish_amt: float = 0.3
    film_nm: float = 60.0
    lines: float = 0.5
    specks: float = 0.4
    metallic: float = 1.0
    anneal: bool = False


# Linear-RGB reflectance values for the clean metal; "factory new" amounts of wear.
METALS: dict[str, Metal] = {
    "brass": Metal((0.88, 0.70, 0.34), (1.00, 0.94, 0.80), 0.14, tarnish=(0.60, 0.44, 0.20), tarnish_amt=0.15, film_nm=40, lines=0.3, specks=0.3, anneal=True),
    "gilding-metal": Metal((0.93, 0.58, 0.40), (1.00, 0.86, 0.76), 0.17, tarnish=(0.55, 0.30, 0.20), tarnish_amt=0.15, film_nm=40, lines=0.3, specks=0.2),
    "copper": Metal((0.955, 0.637, 0.538), (1.00, 0.86, 0.78), 0.28, tarnish=(0.45, 0.25, 0.18), tarnish_amt=0.35, film_nm=70, lines=0.1, specks=0.4),
    "lead": Metal((0.42, 0.43, 0.46), (0.80, 0.80, 0.82), 0.50, roughness_var=0.08, tarnish=(0.55, 0.56, 0.58), tarnish_amt=0.6, film_nm=0, lines=0.0, specks=0.3, metallic=0.9),
    "nickel": Metal((0.66, 0.61, 0.53), (0.90, 0.88, 0.85), 0.12, tarnish=(0.50, 0.48, 0.45), tarnish_amt=0.1, film_nm=20, lines=0.2),
    "steel": Metal((0.56, 0.57, 0.58), (0.85, 0.86, 0.88), 0.25, tarnish=(0.35, 0.25, 0.18), tarnish_amt=0.3, film_nm=40),
    "aluminum": Metal((0.91, 0.92, 0.92), (0.97, 0.97, 0.98), 0.25, tarnish=(0.75, 0.76, 0.77), tarnish_amt=0.3, film_nm=0),
}

ANNEAL_COLOUR = (0.32, 0.22, 0.20)


def _sock(sockets, key):
    for s in sockets:
        if s.identifier == key:
            return s
    return sockets[key]


class _G:
    """Tiny helper for building node trees."""

    def __init__(self, nt):
        self.nt = nt
        self.col = 0

    def node(self, kind, x=0, y=0, inputs=None, **attrs):
        n = self.nt.nodes.new(kind)
        n.location = (x, y)
        for k, v in attrs.items():
            setattr(n, k, v)
        for k, v in (inputs or {}).items():
            self.feed(_sock(n.inputs, k), v)
        return n

    def feed(self, socket, value):
        if isinstance(value, bpy.types.NodeSocket):
            self.nt.links.new(value, socket)
        else:
            socket.default_value = value

    def math(self, op, a, b=0.0, x=0, y=0, clamp=False):
        n = self.node("ShaderNodeMath", x, y, operation=op, use_clamp=clamp)
        self.feed(n.inputs[0], a)
        self.feed(n.inputs[1], b)
        return n.outputs[0]

    def map(self, v, fmin, fmax, tmin=0.0, tmax=1.0, x=0, y=0, smooth=False):
        n = self.node("ShaderNodeMapRange", x, y, clamp=True)
        if smooth:
            n.interpolation_type = "SMOOTHSTEP"
        for key, val in (("Value", v), ("From Min", fmin), ("From Max", fmax), ("To Min", tmin), ("To Max", tmax)):
            self.feed(n.inputs[key], val)
        return n.outputs[0]

    def noise(self, vec, w, scale, detail, rough=0.55, x=0, y=0):
        n = self.node("ShaderNodeTexNoise", x, y, noise_dimensions="4D")
        self.feed(n.inputs["Vector"], vec)
        self.feed(n.inputs["W"], w)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        return n.outputs["Fac"]

    def mix(self, fac, a, b, x=0, y=0):
        n = self.node("ShaderNodeMix", x, y, data_type="RGBA")
        self.feed(_sock(n.inputs, "Factor_Float"), fac)
        self.feed(_sock(n.inputs, "A_Color"), a)
        self.feed(_sock(n.inputs, "B_Color"), b)
        return _sock(n.outputs, "Result_Color")

    def attr(self, name, x=0, y=0):
        return self.node("ShaderNodeAttribute", x, y, attribute_type="OBJECT", attribute_name=name).outputs["Fac"]


def _new(name):
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            mat.use_nodes = True
    mat.node_tree.nodes.clear()
    return mat


def metal_material(key: str) -> bpy.types.Material:
    existing = bpy.data.materials.get(key)
    if existing:
        return existing
    p = METALS[key]
    mat = _new(key)
    g = _G(mat.node_tree)

    tc = g.node("ShaderNodeTexCoord", -1400, 0)
    pmm = g.node("ShaderNodeVectorMath", -1200, 0, operation="SCALE")
    g.feed(pmm.inputs[0], tc.outputs["Object"])
    _sock(pmm.inputs, "Scale").default_value = 1000.0  # metres -> millimetres
    pmm = pmm.outputs[0]
    rnd = g.node("ShaderNodeObjectInfo", -1400, -300).outputs["Random"]
    w = g.math("MULTIPLY", rnd, 173.0, -1200, -300)

    # tarnish blotches
    blotch = g.noise(pmm, w, scale=0.25, detail=3.0, x=-1000, y=300)
    tarnish = g.math("MULTIPLY", g.map(blotch, 0.48, 0.72, x=-800, y=300, smooth=True), p.tarnish_amt, -600, 300)
    # fine roughness variation
    fine = g.map(g.noise(pmm, w, scale=3.0, detail=6.0, rough=0.6, x=-1000, y=0), 0.3, 0.7, -1.0, 1.0, x=-800, y=0)
    # drawing marks: noise stretched along the part axis
    stretch = g.node("ShaderNodeVectorMath", -1000, -250, operation="MULTIPLY")
    g.feed(stretch.inputs[0], pmm)
    stretch.inputs[1].default_value = (6.0, 6.0, 0.08)
    lines = g.math("MULTIPLY", g.map(g.noise(stretch.outputs[0], w, 1.0, 2.0, x=-800, y=-250), 0.5, 0.8, x=-600, y=-250), p.lines, -400, -250)
    # sparse tiny dings
    w2 = g.math("ADD", w, 11.0, -1000, -500)
    specks = g.math("MULTIPLY", g.map(g.noise(pmm, w2, 1.8, 1.0, x=-800, y=-500), 0.78, 0.81, x=-600, y=-500), p.specks, -400, -500)

    rough = g.math("MULTIPLY", fine, p.roughness_var, -400, 0)
    rough = g.math("ADD", rough, p.roughness, -250, 0)
    rough = g.math("ADD", rough, g.math("MULTIPLY", lines, 0.05, -250, -150), -100, 0)
    rough = g.math("ADD", rough, g.math("MULTIPLY", specks, 0.12, -250, -300), 50, 0)
    rough = g.math("ADD", rough, g.math("MULTIPLY", tarnish, 0.10, -250, 150), 200, 0)
    jitter = g.math("MULTIPLY", g.math("SUBTRACT", rnd, 0.5, -400, -650), 0.04, -250, -650)
    rough = g.math("ADD", rough, jitter, 350, 0, clamp=True)

    colour = g.mix(g.math("MULTIPLY", tarnish, 0.5, -400, 450), (*p.base, 1.0), (*p.tarnish, 1.0), -200, 450)
    film = g.math("MULTIPLY", tarnish, p.film_nm, -200, 650)

    if p.anneal:
        z = g.node("ShaderNodeSeparateXYZ", -1000, 800)
        g.feed(z.inputs[0], pmm)
        band = g.map(z.outputs["Z"], g.attr("anneal_z0", -1000, 1000), g.attr("anneal_z1", -1000, 1150), x=-800, y=900, smooth=True)
        amt = g.math("MULTIPLY", band, g.attr("anneal_amt", -800, 1100), -600, 900)
        streak = g.map(blotch, 0.2, 0.8, 0.85, 1.15, x=-600, y=1100)
        anneal = g.math("MULTIPLY", amt, streak, -400, 900, clamp=True)
        colour = g.mix(g.math("MULTIPLY", anneal, 0.35, -200, 900), colour, (*ANNEAL_COLOUR, 1.0), 0, 600)
        film = g.math("ADD", film, g.math("MULTIPLY", anneal, 200.0, -200, 1100), 0, 800)

    # residue settles in recesses (headstamp letters, extractor groove): darken by local occlusion
    ao = g.node("ShaderNodeAmbientOcclusion", 0, 1000, only_local=True, samples=8, inputs={"Distance": 0.0004})
    cavity = g.math("MULTIPLY", g.math("SUBTRACT", 1.0, ao.outputs["AO"], 200, 1000), 0.6, 350, 1000, clamp=True)
    colour = g.mix(cavity, colour, (*(c * 0.35 for c in p.tarnish), 1.0), 500, 800)

    height = g.math("ADD", g.math("MULTIPLY", lines, 0.25, -100, -400), g.math("MULTIPLY", fine, 0.04, -100, -550), 50, -450)
    height = g.math("SUBTRACT", height, specks, 200, -450)
    bump = g.node("ShaderNodeBump", 350, -450, inputs={"Strength": 0.2, "Distance": 0.00001, "Height": height})

    bsdf = g.node(
        "ShaderNodeBsdfPrincipled",
        600,
        200,
        inputs={
            "Base Color": colour,
            "Metallic": p.metallic,
            "Roughness": rough,
            "Specular Tint": (*p.edge, 1.0),
            "Thin Film Thickness": film,
            "Thin Film IOR": 2.0,
            "Normal": bump.outputs["Normal"],
        },
    )
    out = g.node("ShaderNodeOutputMaterial", 900, 200)
    g.feed(out.inputs["Surface"], bsdf.outputs["BSDF"])
    return mat


def ground_material() -> bpy.types.Material:
    mat = bpy.data.materials.get("ground") or _new("ground")
    if mat.node_tree.nodes:
        return mat
    g = _G(mat.node_tree)
    tc = g.node("ShaderNodeTexCoord", -800, 0)
    n = g.node("ShaderNodeTexNoise", -600, 0, inputs={"Scale": 40.0, "Detail": 8.0})
    g.feed(n.inputs["Vector"], tc.outputs["Object"])
    v = g.map(n.outputs["Fac"], 0.3, 0.7, 0.16, 0.20, x=-400, y=0)
    bsdf = g.node("ShaderNodeBsdfPrincipled", 0, 0, inputs={"Base Color": (0.18, 0.18, 0.18, 1.0), "Roughness": 0.6})
    cr = g.node("ShaderNodeCombineColor", -200, 0)
    for i in range(3):
        g.feed(cr.inputs[i], v)
    g.feed(bsdf.inputs["Base Color"], cr.outputs[0])
    out = g.node("ShaderNodeOutputMaterial", 300, 0)
    g.feed(out.inputs["Surface"], bsdf.outputs["BSDF"])
    return mat


def studio_world() -> None:
    """Soft vertical gradient so metals have something to reflect."""
    world = bpy.context.scene.world or bpy.data.worlds.new("studio")
    bpy.context.scene.world = world
    if world.node_tree is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    g = _G(nt)
    tc = g.node("ShaderNodeTexCoord", -800, 0)
    z = g.node("ShaderNodeSeparateXYZ", -600, 0)
    g.feed(z.inputs[0], tc.outputs["Generated"])
    ramp = g.node("ShaderNodeValToRGB", -400, 0)
    g.feed(ramp.inputs["Fac"], g.map(z.outputs["Z"], -0.3, 1.0, x=-500, y=-200))
    ramp.color_ramp.elements[0].color = (0.02, 0.02, 0.022, 1)
    ramp.color_ramp.elements[1].color = (0.55, 0.56, 0.60, 1)
    mid = ramp.color_ramp.elements.new(0.45)
    mid.color = (0.12, 0.12, 0.13, 1)
    bg = g.node("ShaderNodeBackground", 0, 0, inputs={"Strength": 0.35})
    g.feed(bg.inputs["Color"], ramp.outputs["Color"])
    out = g.node("ShaderNodeOutputWorld", 250, 0)
    g.feed(out.inputs["Surface"], bg.outputs["Background"])
