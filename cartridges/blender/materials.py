"""Procedural, physically based metal materials, kept light for EEVEE (also fine in Cycles).

All metals share one node graph with per-metal parameters:

* base colour = measured normal-incidence reflectance (linear RGB), edge tint = F82 tint
* two 4D noises (low and high frequency) whose three colour channels drive six masks:
  tarnish blotches, slow roughness drift, anneal streaks, fine roughness, sparse specks
* drawing marks along the part's axis, and sparse micro-dents (a Voronoi dimple field)
* a baked ``cavity`` vertex attribute (headstamp letters, primer gap, extractor groove,
  case interior) darkens and roughens recesses, standing in for ambient occlusion, which
  is costly in EEVEE
* brass only: an annealing stain on rifle necks, from object properties ``anneal_z0`` /
  ``anneal_z1`` (mm from the head) and ``anneal_amt`` (0-1)

Texture space is object space in millimetres, offset by the object's random value, so
every copy gets its own pattern.
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
    dimples: float = 0.6
    metallic: float = 1.0
    anneal: bool = False


METALS: dict[str, Metal] = {
    "brass": Metal((0.88, 0.70, 0.34), (1.00, 0.94, 0.80), 0.15, tarnish=(0.60, 0.44, 0.20), tarnish_amt=0.22, film_nm=40, lines=0.3, specks=0.4, anneal=True),
    "gilding-metal": Metal((0.93, 0.58, 0.40), (1.00, 0.86, 0.76), 0.18, tarnish=(0.55, 0.30, 0.20), tarnish_amt=0.20, film_nm=40, lines=0.3, specks=0.3, dimples=0.4),
    "copper": Metal((0.955, 0.637, 0.538), (1.00, 0.86, 0.78), 0.28, tarnish=(0.45, 0.25, 0.18), tarnish_amt=0.35, film_nm=70, lines=0.1, specks=0.4, dimples=0.4),
    "lead": Metal((0.42, 0.43, 0.46), (0.80, 0.80, 0.82), 0.50, roughness_var=0.08, tarnish=(0.55, 0.56, 0.58), tarnish_amt=0.6, film_nm=0, lines=0.0, specks=0.3, dimples=0.8, metallic=0.9),
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

    def madd(self, a, b, c, x=0, y=0, clamp=False):
        """a * b + c"""
        n = self.node("ShaderNodeMath", x, y, operation="MULTIPLY_ADD", use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            self.feed(n.inputs[i], v)
        return n.outputs[0]

    def map(self, v, fmin, fmax, tmin=0.0, tmax=1.0, x=0, y=0, smooth=False):
        n = self.node("ShaderNodeMapRange", x, y, clamp=True)
        if smooth:
            n.interpolation_type = "SMOOTHSTEP"
        for key, val in (("Value", v), ("From Min", fmin), ("From Max", fmax), ("To Min", tmin), ("To Max", tmax)):
            self.feed(n.inputs[key], val)
        return n.outputs[0]

    def noise_rgb(self, vec, w, scale, detail, x=0, y=0):
        n = self.node("ShaderNodeTexNoise", x, y, noise_dimensions="4D")
        self.feed(n.inputs["Vector"], vec)
        self.feed(n.inputs["W"], w)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = 0.5
        sep = self.node("ShaderNodeSeparateColor", x + 180, y)
        self.feed(sep.inputs[0], n.outputs["Color"])
        return n.outputs["Fac"], sep.outputs[0], sep.outputs[1], sep.outputs[2]

    def mix(self, fac, a, b, x=0, y=0):
        n = self.node("ShaderNodeMix", x, y, data_type="RGBA")
        self.feed(_sock(n.inputs, "Factor_Float"), fac)
        self.feed(_sock(n.inputs, "A_Color"), a)
        self.feed(_sock(n.inputs, "B_Color"), b)
        return _sock(n.outputs, "Result_Color")

    def attr(self, name, kind="OBJECT", x=0, y=0):
        return self.node("ShaderNodeAttribute", x, y, attribute_type=kind, attribute_name=name).outputs["Fac"]


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

    tc = g.node("ShaderNodeTexCoord", -1600, 0)
    pmm = g.node("ShaderNodeVectorMath", -1400, 0, operation="SCALE")
    g.feed(pmm.inputs[0], tc.outputs["Object"])
    _sock(pmm.inputs, "Scale").default_value = 1000.0  # metres -> millimetres
    pmm = pmm.outputs[0]
    info = g.node("ShaderNodeObjectInfo", -1600, -300)
    rnd = info.outputs["Random"]
    w = g.math("MULTIPLY", rnd, 173.0, -1400, -300)
    # per-object drivers packed in the object colour (EEVEE reads it as a plain uniform):
    #   R dirt, G soot inside, B soot outside, A anneal amount
    drivers = g.node("ShaderNodeSeparateColor", -1400, 1700)
    g.feed(drivers.inputs[0], info.outputs["Color"])
    dirt_amt, soot_in_amt, soot_out_amt = drivers.outputs[0], drivers.outputs[1], drivers.outputs[2]
    anneal_amt = info.outputs["Alpha"]

    # low-frequency channels: tarnish blotches, roughness drift, anneal streaks
    _, lo_r, lo_g, lo_b = g.noise_rgb(pmm, w, 0.25, 2.0, -1200, 400)
    tarnish = g.math("MULTIPLY", g.map(lo_r, 0.45, 0.75, x=-800, y=500, smooth=True), p.tarnish_amt, -600, 500)
    drift = g.map(lo_g, 0.3, 0.7, -1.0, 1.0, x=-800, y=350)
    # high-frequency channels: fine roughness, specks
    _, hi_r, hi_g, _ = g.noise_rgb(pmm, w, 3.0, 2.0, -1200, 0)
    fine = g.map(hi_r, 0.3, 0.7, -1.0, 1.0, x=-800, y=50)
    specks = g.math("MULTIPLY", g.map(hi_g, 0.76, 0.79, x=-800, y=-100), p.specks, -600, -100)
    # drawing marks along the axis
    stretch = g.node("ShaderNodeVectorMath", -1400, -550, operation="MULTIPLY")
    g.feed(stretch.inputs[0], pmm)
    stretch.inputs[1].default_value = (6.0, 6.0, 0.08)
    lines_fac, _, _, _ = g.noise_rgb(stretch.outputs[0], w, 1.0, 1.0, -1200, -550)
    lines = g.math("MULTIPLY", g.map(lines_fac, 0.5, 0.8, x=-800, y=-550), p.lines, -600, -550)
    # sparse micro-dents from bulk handling: smooth dimples in a few Voronoi cells
    vor = g.node("ShaderNodeTexVoronoi", -1200, -850, voronoi_dimensions="4D", feature="F1")
    g.feed(vor.inputs["Vector"], pmm)
    g.feed(vor.inputs["W"], w)
    vor.inputs["Scale"].default_value = 0.9
    cell = g.node("ShaderNodeSeparateColor", -1000, -950)
    g.feed(cell.inputs[0], vor.outputs["Color"])
    pick = g.map(cell.outputs[0], 0.82, 0.86, x=-800, y=-950)
    bowl = g.map(vor.outputs["Distance"], 0.0, 0.45, 1.0, 0.0, x=-800, y=-800, smooth=True)
    dimple = g.math("MULTIPLY", g.math("MULTIPLY", bowl, pick, -600, -850), p.dimples, -450, -850)

    cavity = g.attr("cavity", "GEOMETRY", -800, 800)

    rough = g.madd(fine, p.roughness_var * 0.35, p.roughness, -400, 0)
    rough = g.madd(drift, p.roughness_var * 0.5, rough, -250, 0)
    rough = g.madd(lines, 0.04, rough, -100, 0)
    rough = g.madd(specks, 0.10, rough, 50, 0)
    rough = g.madd(tarnish, 0.10, rough, 200, 0)
    rough = g.madd(cavity, 0.25, rough, 350, 0)
    rough = g.madd(g.math("SUBTRACT", rnd, 0.5, -400, -250), 0.04, rough, 500, 0, clamp=True)

    colour = g.mix(g.math("MULTIPLY", tarnish, 0.5, -400, 650), (*p.base, 1.0), (*p.tarnish, 1.0), -200, 650)
    film = g.math("MULTIPLY", tarnish, p.film_nm, -200, 850)

    if p.anneal:
        amt = g.math("MULTIPLY", g.attr("anneal", "GEOMETRY", -1000, 1150), anneal_amt, -800, 1150)  # band baked per vertex
        anneal = g.math("MULTIPLY", amt, g.map(lo_b, 0.2, 0.8, 0.85, 1.15, x=-800, y=1350), -600, 1150, clamp=True)
        # colour only: a thin film passes through dark interference bands in this thickness range
        colour = g.mix(g.math("MULTIPLY", anneal, 0.3, -400, 1150), colour, (*ANNEAL_COLOUR, 1.0), 0, 900)

    grime = tuple(c * 0.35 for c in p.tarnish)
    colour = g.mix(g.math("MULTIPLY", cavity, 0.7, 200, 800), colour, (*grime, 1.0), 350, 700)

    # ---- dirt and soot (amounts from the object colour, see above; scene.make_copy sets them):
    #   dirt      soil/dust coverage; collects in recesses first
    #   soot in   powder residue inside a fired case, heaviest at the bottom
    #   soot out  blow-by on the outside of a fired case's neck/mouth
    zn = g.attr("zn", "GEOMETRY", -1200, 1900)  # height along the case, 0 at the head, 1 at the mouth
    w3 = g.math("ADD", w, 31.0, -1200, 2300)
    soil_fac, soil_r, _, soil_b = g.noise_rgb(pmm, w3, 0.6, 4.0, -1000, 2300)
    lo_cut = g.madd(dirt_amt, -0.75, 1.08, -800, 2450)  # more dirt, lower threshold, wider patches
    patches = g.map(soil_fac, lo_cut, g.math("ADD", lo_cut, 0.15, -800, 2550), x=-600, y=2400, smooth=True)
    dirt = g.madd(cavity, dirt_amt, g.math("MULTIPLY", patches, dirt_amt, -400, 2400), -250, 2350)
    dirt = g.madd(dirt_amt, 0.12, dirt, -100, 2350, clamp=True)  # thin dust film everywhere
    soil = g.mix(soil_b, (0.03, 0.024, 0.017, 1.0), (0.11, 0.085, 0.06, 1.0), -400, 2150)
    # brass that has lain in the dirt is tarnished and dull under the soil too
    weathered = g.madd(g.map(lo_r, 0.3, 0.7, 0.4, 1.0, x=-400, y=1950), g.math("MULTIPLY", dirt_amt, 0.55, -400, 1850), 0.0, -250, 1900)
    colour = g.mix(weathered, colour, (*grime, 1.0), 400, 1300)
    rough = g.madd(dirt_amt, 0.2, rough, 400, 150)

    interior = g.attr("interior", "GEOMETRY", -1000, 2700)
    falloff = g.map(zn, 0.05, 0.95, 1.5, 1.0, x=-800, y=2750, smooth=True)  # heaviest at the floor, by the flash hole
    soot_in = g.math("MULTIPLY", g.math("MULTIPLY", interior, soot_in_amt, -800, 2900), falloff, -600, 2850)
    soot_in = g.math("MULTIPLY", soot_in, g.map(lo_b, 0.3, 0.7, 0.8, 1.2, x=-800, y=3050), -450, 2900, clamp=True)
    outside = g.math("SUBTRACT", 1.0, interior, -800, 3200)
    neck = g.map(zn, 0.62, 0.96, x=-800, y=3350, smooth=True)
    streak = g.map(lines_fac, 0.35, 0.75, 0.4, 1.0, x=-800, y=3500)
    soot_out = g.math("MULTIPLY", g.math("MULTIPLY", outside, neck, -600, 3250), g.math("MULTIPLY", soot_out_amt, streak, -600, 3600), -450, 3400, clamp=True)
    soot = g.math("ADD", soot_in, soot_out, -300, 3100, clamp=True)
    # soot is patchy, not a tint: a spot is either sooted or bare (a half-blend reads as pale paint)
    soot = g.map(soot, 0.3, 0.6, x=-150, y=3100, smooth=True)

    colour = g.mix(dirt, colour, soil, 500, 1200)
    colour = g.mix(soot, colour, (0.018, 0.016, 0.014, 1.0), 650, 1200)
    # only real soil cover stops being metal; a dust film over brass still reflects like brass
    caked = g.map(dirt, 0.35, 0.75, x=500, y=1650, smooth=True)
    metallic = g.math("MULTIPLY", g.math("SUBTRACT", 1.0, g.math("MULTIPLY", caked, 0.9, 500, 1500), 650, 1500), p.metallic, 800, 1500)
    metallic = g.math("MULTIPLY", metallic, g.math("SUBTRACT", 1.0, soot, 800, 1650, clamp=True), 950, 1550)  # soot is matte carbon, not metal
    rough = g.madd(dirt, g.math("SUBTRACT", 0.9, rough, 550, 100), rough, 700, 50)
    rough = g.madd(soot, g.math("SUBTRACT", 0.6, rough, 750, 100), rough, 850, 50)

    height = g.math("MULTIPLY", lines, 0.2, 50, -450)  # fine noise stays out of the bump: it reads as grain
    height = g.madd(specks, -0.6, height, 200, -450)
    height = g.madd(dimple, -0.6, height, 300, -600)
    height = g.madd(g.math("MULTIPLY", dirt, soil_r, 300, -750), 1.5, height, 400, -700)  # soil grains stand proud
    bump = g.node("ShaderNodeBump", 450, -450, inputs={"Strength": 0.2, "Distance": 0.00001, "Height": height})

    bsdf = g.node(
        "ShaderNodeBsdfPrincipled",
        1100,
        200,
        inputs={
            "Base Color": colour,
            "Metallic": metallic,
            "Roughness": rough,
            "Specular Tint": (*p.edge, 1.0),
            "Thin Film Thickness": film,
            "Thin Film IOR": 2.0,
            "Normal": bump.outputs["Normal"],
        },
    )
    out = g.node("ShaderNodeOutputMaterial", 1400, 200)
    g.feed(out.inputs["Surface"], bsdf.outputs["BSDF"])
    return mat


def ground_material() -> bpy.types.Material:
    mat = bpy.data.materials.get("ground") or _new("ground")
    if mat.node_tree.nodes:
        return mat
    g = _G(mat.node_tree)
    tc = g.node("ShaderNodeTexCoord", -800, 0)
    n = g.node("ShaderNodeTexNoise", -600, 0, inputs={"Scale": 40.0, "Detail": 4.0})
    g.feed(n.inputs["Vector"], tc.outputs["Object"])
    v = g.map(n.outputs["Fac"], 0.3, 0.7, 0.16, 0.20, x=-400, y=0)
    cr = g.node("ShaderNodeCombineColor", -200, 0)
    for i in range(3):
        g.feed(cr.inputs[i], v)
    bsdf = g.node("ShaderNodeBsdfPrincipled", 0, 0, inputs={"Roughness": 0.6})
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
    ramp.color_ramp.elements[0].color = (0.05, 0.05, 0.055, 1)
    ramp.color_ramp.elements[1].color = (0.70, 0.71, 0.75, 1)
    mid = ramp.color_ramp.elements.new(0.45)
    mid.color = (0.22, 0.22, 0.23, 1)
    bg = g.node("ShaderNodeBackground", 0, 0, inputs={"Strength": 0.35})
    g.feed(bg.inputs["Color"], ramp.outputs["Color"])
    out = g.node("ShaderNodeOutputWorld", 250, 0)
    g.feed(out.inputs["Surface"], bg.outputs["Background"])
