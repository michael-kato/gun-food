"""Procedural, physically based metal materials, kept light for EEVEE (also fine in Cycles).

One shared node group, ``GF Metal``, holds the whole look; every metal material (brass,
gilding metal, copper, lead, nickel, steel, aluminium) is just an instance of that group
with its own inputs. Edit the group once and every material follows. Every copy of a part
shares its metal's material; per-copy variation comes from the object (random value,
object colour) and the mesh (baked attributes), never from material copies.

Inside the group:

* metal layer: measured normal-incidence reflectance (linear RGB) as base colour, F82
  edge tint, tarnish blotches with a thin oxide film, drawing marks along the axis, sparse
  specks and micro-dents, recess grime from the baked ``cavity`` attribute (instead of
  costly ambient occlusion), and an annealing tint on rifle necks (``anneal`` attribute)
* dirt layer: dielectric soil with its own grainy surface; collects in recesses first
* soot layer: matte carbon inside fired cases (heaviest at the floor) and blow-by
  streaks on the neck

The three layers are complete BSDFs mixed as closures, like Unreal Substrate slabs: masks
only set coverage, so mask edges never produce half-metallic, pale-looking brass.

* sealant layer: primer lacquer (purple, red, blue, ...) in a ring at the cup's edge, sometimes
  run over part of the face

Per-copy drivers live in the object colour (R dirt, G soot inside, B soot outside,
A annealing amount) and in object properties: ``gf_age`` (tarnish spreads, streaks and
darkens), ``gf_wear`` (scratches along the case), and on primers ``gf_seal`` (sealant
colour, black for none) and ``gf_smear``. Texture space is object space in millimetres,
offset by the object's random value, so every copy gets its own pattern.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import bpy

GROUP = "GF Metal"


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
    "lead": Metal((0.28, 0.285, 0.30), (0.70, 0.70, 0.72), 0.6, roughness_var=0.08, tarnish=(0.20, 0.20, 0.21), tarnish_amt=0.5, film_nm=0, lines=0.0, specks=0.3, dimples=0.8, metallic=0.75),
    "nickel": Metal((0.66, 0.61, 0.53), (0.90, 0.88, 0.85), 0.12, tarnish=(0.50, 0.48, 0.45), tarnish_amt=0.1, film_nm=20, lines=0.2),
    "steel": Metal((0.56, 0.57, 0.58), (0.85, 0.86, 0.88), 0.25, tarnish=(0.35, 0.25, 0.18), tarnish_amt=0.3, film_nm=40),
    "aluminum": Metal((0.91, 0.92, 0.92), (0.97, 0.97, 0.98), 0.32, tarnish=(0.75, 0.76, 0.77), tarnish_amt=0.3, film_nm=0),
    # steel cases: a grey polymer coat or a green-grey lacquer over the steel (dielectric-ish)
    "steel-polymer": Metal((0.060, 0.062, 0.060), (0.30, 0.30, 0.30), 0.45, roughness_var=0.06, tarnish=(0.08, 0.08, 0.075), tarnish_amt=0.1, film_nm=0, lines=0.15, specks=0.5, dimples=0.5, metallic=0.25),
    "steel-lacquer": Metal((0.050, 0.055, 0.032), (0.30, 0.30, 0.26), 0.28, roughness_var=0.05, tarnish=(0.10, 0.09, 0.06), tarnish_amt=0.15, film_nm=0, lines=0.1, specks=0.4, dimples=0.5, metallic=0.2),
}


def paint(rgb) -> Metal:
    """Bullet tip paint: a dielectric with the given linear RGB."""
    return Metal(tuple(rgb), (1.0, 1.0, 1.0), 0.45, roughness_var=0.08, tarnish=tuple(0.6 * c for c in rgb), tarnish_amt=0.0, film_nm=0, lines=0.0, specks=0.2, dimples=0.0, metallic=0.0)

# Group inputs: (name, socket type, default)
INPUTS = [
    ("Base Color", "NodeSocketColor", (0.88, 0.70, 0.34, 1.0)),
    ("Edge Tint", "NodeSocketColor", (1.0, 0.94, 0.80, 1.0)),
    ("Metallic", "NodeSocketFloat", 1.0),
    ("Roughness", "NodeSocketFloat", 0.15),
    ("Roughness Variation", "NodeSocketFloat", 0.03),
    ("Tarnish Color", "NodeSocketColor", (0.6, 0.44, 0.2, 1.0)),
    ("Tarnish", "NodeSocketFloat", 0.2),
    ("Oxide Film (nm)", "NodeSocketFloat", 40.0),
    ("Drawing Marks", "NodeSocketFloat", 0.3),
    ("Specks", "NodeSocketFloat", 0.4),
    ("Micro Dents", "NodeSocketFloat", 0.6),
    ("Annealing", "NodeSocketFloat", 0.0),
]

ANNEAL_FRINGE = (0.30, 0.17, 0.10, 1.0)  # straw-brown where the heat faded out
ANNEAL_CORE = (0.22, 0.21, 0.24, 1.0)  # blue-grey on the neck, where it was hottest
SOIL_DARK = (0.025, 0.019, 0.013, 1.0)
SOIL_LIGHT = (0.085, 0.064, 0.042, 1.0)
SOOT = (0.014, 0.013, 0.012, 1.0)


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

    def attr(self, name, kind="GEOMETRY", x=0, y=0):
        return self.node("ShaderNodeAttribute", x, y, attribute_type=kind, attribute_name=name).outputs["Fac"]

    def bsdf(self, x, y, **inputs):
        return self.node("ShaderNodeBsdfPrincipled", x, y, inputs={k.replace("_", " "): v for k, v in inputs.items()}).outputs["BSDF"]

    def mix_shader(self, fac, a, b, x=0, y=0):
        n = self.node("ShaderNodeMixShader", x, y)
        self.feed(n.inputs[0], fac)
        self.feed(n.inputs[1], a)
        self.feed(n.inputs[2], b)
        return n.outputs[0]


def _new(name):
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            mat.use_nodes = True
    mat.node_tree.nodes.clear()
    return mat


def metal_group() -> bpy.types.ShaderNodeTree:
    """The shared ``GF Metal`` node group (built once per file)."""
    ng = bpy.data.node_groups.get(GROUP)
    if ng:
        return ng
    ng = bpy.data.node_groups.new(GROUP, "ShaderNodeTree")
    for name, kind, default in INPUTS:
        sock = ng.interface.new_socket(name, in_out="INPUT", socket_type=kind)
        sock.default_value = default
    ng.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    g = _G(ng)
    gi = g.node("NodeGroupInput", -2000, 0).outputs
    go = g.node("NodeGroupOutput", 2100, 0)

    tc = g.node("ShaderNodeTexCoord", -1800, 0)
    pmm = g.node("ShaderNodeVectorMath", -1600, 0, operation="SCALE")
    g.feed(pmm.inputs[0], tc.outputs["Object"])
    _sock(pmm.inputs, "Scale").default_value = 1000.0  # metres -> millimetres
    pmm = pmm.outputs[0]
    info = g.node("ShaderNodeObjectInfo", -1800, -300)
    rnd = info.outputs["Random"]
    w = g.math("MULTIPLY", rnd, 173.0, -1600, -300)
    # per-object drivers packed in the object colour: R dirt, G soot in, B soot out, A anneal
    drivers = g.node("ShaderNodeSeparateColor", -1600, 1700)
    g.feed(drivers.inputs[0], info.outputs["Color"])
    dirt_amt, soot_in_amt, soot_out_amt = drivers.outputs[0], drivers.outputs[1], drivers.outputs[2]
    anneal_amt = info.outputs["Alpha"]

    # ---- shared noise channels
    _, lo_r, lo_g, lo_b = g.noise_rgb(pmm, w, 0.25, 2.0, -1400, 400)  # tarnish, drift, anneal streaks
    _, hi_r, hi_g, _ = g.noise_rgb(pmm, w, 3.0, 2.0, -1400, 0)  # fine roughness, specks
    stretch = g.node("ShaderNodeVectorMath", -1600, -550, operation="MULTIPLY")
    g.feed(stretch.inputs[0], pmm)
    stretch.inputs[1].default_value = (6.0, 6.0, 0.08)
    lines_fac, _, _, _ = g.noise_rgb(stretch.outputs[0], w, 1.0, 1.0, -1400, -550)  # drawing marks along the axis
    vor = g.node("ShaderNodeTexVoronoi", -1400, -850, voronoi_dimensions="4D", feature="F1")
    g.feed(vor.inputs["Vector"], pmm)
    g.feed(vor.inputs["W"], w)
    vor.inputs["Scale"].default_value = 0.9
    cell = g.node("ShaderNodeSeparateColor", -1200, -950)
    g.feed(cell.inputs[0], vor.outputs["Color"])

    drift = g.map(lo_g, 0.3, 0.7, -1.0, 1.0, x=-1000, y=350)
    fine = g.map(hi_r, 0.3, 0.7, -1.0, 1.0, x=-1000, y=50)
    specks = g.math("MULTIPLY", g.map(hi_g, 0.76, 0.79, x=-1000, y=-100), gi["Specks"], -800, -100)
    lines = g.math("MULTIPLY", g.map(lines_fac, 0.5, 0.8, x=-1000, y=-550), gi["Drawing Marks"], -800, -550)
    bowl = g.map(vor.outputs["Distance"], 0.0, 0.45, 1.0, 0.0, x=-1000, y=-800, smooth=True)
    pick = g.map(cell.outputs[0], 0.82, 0.86, x=-1000, y=-950)
    dimple = g.math("MULTIPLY", g.math("MULTIPLY", bowl, pick, -800, -850), gi["Micro Dents"], -650, -850)
    cavity = g.attr("cavity", x=-1000, y=800)
    zn = g.attr("zn", x=-1400, y=1900)  # height along the case, 0 head .. 1 mouth
    interior = g.attr("interior", x=-1200, y=2700)
    # per-copy object properties (EEVEE allows 8 such uniforms per material; keep it at 4)
    age = g.attr("gf_age", "OBJECT", x=-1600, y=650)  # tarnish with age, 0-1
    wear = g.attr("gf_wear", "OBJECT", x=-1600, y=-1250)  # scratches and scuffs, 0-1

    # ---- age: blotches spread, streaks along the case appear, the tarnish darkens
    t_lo = g.madd(age, -0.30, 0.45, -1200, 650)
    blot = g.map(lo_r, t_lo, g.math("ADD", t_lo, 0.30, -1100, 700), x=-1000, y=650, smooth=True)
    st_vec = g.node("ShaderNodeVectorMath", -1600, 550, operation="MULTIPLY")
    g.feed(st_vec.inputs[0], pmm)
    st_vec.inputs[1].default_value = (2.5, 2.5, 0.10)
    streak_fac, _, _, _ = g.noise_rgb(st_vec.outputs[0], w, 1.0, 2.0, -1400, 550)
    s_lo = g.madd(age, -0.25, 0.62, -1200, 500)
    streaks = g.math("MULTIPLY", g.map(streak_fac, s_lo, g.math("ADD", s_lo, 0.12, -1100, 450), x=-1000, y=450, smooth=True), age, -850, 450)
    t_amt = g.madd(age, 0.85, gi["Tarnish"], -850, 600, clamp=True)

    # ---- wear: fine scratches along the case (chamber, magazine, ejection), bright in tarnish
    sc_vec = g.node("ShaderNodeVectorMath", -1600, -1150, operation="MULTIPLY")
    g.feed(sc_vec.inputs[0], pmm)
    sc_vec.inputs[1].default_value = (10.0, 10.0, 0.18)
    sc_fac, _, _, _ = g.noise_rgb(sc_vec.outputs[0], w, 1.0, 0.0, -1400, -1150)
    sc_line = g.map(g.math("ABSOLUTE", g.math("SUBTRACT", sc_fac, 0.5, -1200, -1150), 0.0, -1100, -1150), 0.0, 0.012, 1.0, 0.0, x=-1000, y=-1150)
    sp_vec = g.node("ShaderNodeVectorMath", -1600, -1350, operation="MULTIPLY")
    g.feed(sp_vec.inputs[0], pmm)
    sp_vec.inputs[1].default_value = (1.0, 1.0, 0.3)
    sp_fac, _, _, _ = g.noise_rgb(sp_vec.outputs[0], g.math("ADD", w, 7.0, -1600, -1450), 0.8, 1.0, -1400, -1350)
    sp_lo = g.madd(wear, -0.12, 0.60, -1200, -1350)
    sparse = g.map(sp_fac, sp_lo, g.math("ADD", sp_lo, 0.06, -1100, -1400), x=-1000, y=-1350)
    scratch = g.math("MULTIPLY", g.math("MULTIPLY", sc_line, sparse, -850, -1200), wear, -700, -1200, clamp=True)
    unscratched = g.math("SUBTRACT", 1.0, scratch, -550, -1200)

    tarnish = g.math("MULTIPLY", g.math("MULTIPLY", g.math("MAXIMUM", blot, streaks, -800, 550), t_amt, -700, 550), unscratched, -600, 550)

    # ---- metal layer
    rv = gi["Roughness Variation"]
    rough = g.madd(fine, g.math("MULTIPLY", rv, 0.35, -600, 150), gi["Roughness"], -400, 0)
    rough = g.madd(drift, g.math("MULTIPLY", rv, 0.5, -400, 150), rough, -250, 0)
    rough = g.madd(lines, 0.04, rough, -100, 0)
    rough = g.madd(specks, 0.10, rough, 50, 0)
    rough = g.madd(tarnish, 0.10, rough, 200, 0)
    rough = g.madd(age, 0.10, rough, 275, 0)  # old brass is dull all over
    rough = g.madd(scratch, 0.12, rough, 300, -100)
    rough = g.madd(cavity, 0.25, rough, 350, 0)
    rough = g.madd(dirt_amt, 0.2, rough, 450, 0)  # brass that has lain in the dirt is dull
    rough = g.madd(g.math("SUBTRACT", rnd, 0.5, -400, -250), 0.04, rough, 550, 0, clamp=True)

    dark_t = g.node("ShaderNodeVectorMath", -600, 800, operation="SCALE")
    g.feed(dark_t.inputs[0], gi["Tarnish Color"])
    _sock(dark_t.inputs, "Scale").default_value = 0.30
    t_colour = g.mix(g.math("MULTIPLY", age, 0.9, -600, 950), gi["Tarnish Color"], dark_t.outputs[0], -450, 850)
    colour = g.mix(g.math("MULTIPLY", tarnish, 0.95, -600, 650), gi["Base Color"], t_colour, -300, 650)
    film = g.math("MULTIPLY", tarnish, gi["Oxide Film (nm)"], -400, 850)
    # annealing stain: blue-grey on the neck fading through brown into the body
    a_band = g.attr("anneal", x=-1200, y=1150)
    anneal = g.math("MULTIPLY", g.math("MULTIPLY", a_band, anneal_amt, -1000, 1150), gi["Annealing"], -850, 1150)
    anneal = g.math("MULTIPLY", anneal, g.map(lo_b, 0.2, 0.8, 0.8, 1.2, x=-1000, y=1350), -700, 1150, clamp=True)
    a_colour = g.mix(g.map(a_band, 0.3, 1.0, smooth=True, x=-700, y=1300), ANNEAL_FRINGE, ANNEAL_CORE, -550, 1300)
    colour = g.mix(g.math("MULTIPLY", anneal, 0.8, -550, 1150), colour, a_colour, -200, 950)
    rough = g.madd(anneal, 0.08, rough, 600, 0, clamp=True)
    grime = g.node("ShaderNodeVectorMath", -400, 1450, operation="SCALE")
    g.feed(grime.inputs[0], gi["Tarnish Color"])
    _sock(grime.inputs, "Scale").default_value = 0.35
    grime = grime.outputs[0]
    colour = g.mix(g.math("MULTIPLY", cavity, 0.7, -100, 800), colour, grime, 50, 800)
    weathered = g.math("MULTIPLY", g.map(lo_r, 0.3, 0.7, 0.4, 1.0, x=-400, y=1950), g.math("MULTIPLY", dirt_amt, 0.55, -400, 1850), -200, 1900)
    colour = g.mix(weathered, colour, grime, 200, 1000)

    m_height = g.math("MULTIPLY", lines, 0.2, 50, -450)  # fine noise stays out of the bump: it reads as grain
    m_height = g.madd(specks, -0.6, m_height, 200, -450)
    m_height = g.madd(dimple, -0.6, m_height, 300, -600)
    m_height = g.madd(scratch, -0.8, m_height, 350, -700)
    m_normal = g.node("ShaderNodeBump", 450, -450, inputs={"Strength": 0.2, "Distance": 0.00001, "Height": m_height}).outputs["Normal"]
    metal = g.bsdf(
        1000,
        400,
        Base_Color=colour,
        Metallic=gi["Metallic"],
        Roughness=rough,
        Specular_Tint=gi["Edge Tint"],
        Thin_Film_Thickness=film,
        Thin_Film_IOR=2.0,
        Normal=m_normal,
    )

    # ---- dirt layer: soil, patchy, in recesses first, plus a thin film of dust
    w3 = g.math("ADD", w, 31.0, -1400, 2300)
    soil_fac, soil_r, _, soil_b = g.noise_rgb(pmm, w3, 1.1, 4.0, -1200, 2300)
    lo_cut = g.madd(dirt_amt, -0.6, 1.08, -800, 2450)  # more dirt: lower threshold, wider patches
    patches = g.map(soil_fac, lo_cut, g.math("ADD", lo_cut, 0.12, -800, 2550), x=-600, y=2400, smooth=True)
    dirt = g.madd(cavity, dirt_amt, g.math("MULTIPLY", patches, dirt_amt, -400, 2400), -250, 2350)
    dirt = g.madd(dirt_amt, 0.12, dirt, -100, 2350, clamp=True)
    dirt = g.math("MULTIPLY", dirt, g.madd(scratch, -0.7, 1.0, -100, 2250), 0, 2350)  # scratches cut through it
    soil = g.mix(soil_b, SOIL_DARK, SOIL_LIGHT, -400, 2150)
    d_height = g.madd(soil_r, 1.0, g.math("MULTIPLY", dimple, 0.5, 300, -900), 450, -900)
    d_normal = g.node("ShaderNodeBump", 650, -900, inputs={"Strength": 0.6, "Distance": 0.00003, "Height": d_height}).outputs["Normal"]
    soil_rough = g.map(soil_fac, 0.3, 0.7, 0.88, 1.0, x=700, y=-700)
    dirt_bsdf = g.bsdf(1000, -300, Base_Color=soil, Metallic=0.0, Roughness=soil_rough, Specular_IOR_Level=0.2, Normal=d_normal)

    # ---- soot layer: inside a fired case (heaviest at the floor) and blow-by on the neck
    falloff = g.map(zn, 0.05, 0.95, 1.5, 1.0, x=-800, y=2750, smooth=True)
    soot_in = g.math("MULTIPLY", g.math("MULTIPLY", interior, soot_in_amt, -800, 2900), falloff, -600, 2850)
    soot_in = g.math("MULTIPLY", soot_in, g.map(lo_b, 0.3, 0.7, 0.8, 1.2, x=-800, y=3050), -450, 2900, clamp=True)
    outside = g.math("SUBTRACT", 1.0, interior, -800, 3200)
    neck = g.map(zn, 0.62, 0.96, x=-800, y=3350, smooth=True)
    streak = g.map(streak_fac, 0.3, 0.7, 0.35, 1.0, x=-800, y=3500)  # broad blow-by streaks along the neck
    soot_out = g.math("MULTIPLY", g.math("MULTIPLY", outside, neck, -600, 3250), g.math("MULTIPLY", soot_out_amt, streak, -600, 3600), -450, 3400, clamp=True)
    soot = g.map(g.math("ADD", soot_in, soot_out, -300, 3100, clamp=True), 0.05, 0.75, x=-150, y=3100, smooth=True)
    soot_bsdf = g.bsdf(1000, -900, Base_Color=SOOT, Metallic=0.0, Roughness=0.9, Specular_IOR_Level=0.1, Normal=m_normal)

    # ---- primer sealant: lacquer ring where the cup meets the pocket, sometimes run over the
    # face. Only primers carry `rn` (radius / cup radius) and a `gf_seal` colour.
    seal = g.node("ShaderNodeAttribute", -1200, 3900, attribute_type="OBJECT", attribute_name="gf_seal")
    has_seal = g.map(g.node("ShaderNodeVectorMath", -1000, 3900, operation="LENGTH", inputs={0: seal.outputs["Vector"]}).outputs["Value"], 0.0, 0.01, x=-800, y=3900)
    rn = g.madd(g.math("SUBTRACT", hi_r, 0.5, -1000, 4100), 0.08, g.attr("rn", x=-1000, y=4200), -800, 4100)  # ragged inner edge
    ring = g.map(rn, 0.84, 0.90, x=-600, y=4100, smooth=True)
    run = g.madd(g.attr("gf_smear", "OBJECT", x=-1000, y=4400), -0.75, 1.0, -800, 4400)
    blob = g.map(lo_g, run, g.math("ADD", run, 0.05, -700, 4450), x=-600, y=4400, smooth=True)
    seal_cov = g.math("MULTIPLY", g.math("MAXIMUM", ring, blob, -400, 4200), g.math("MULTIPLY", has_seal, 0.95, -400, 4000), -250, 4100)
    seal_bsdf = g.bsdf(1000, -1300, Base_Color=seal.outputs["Color"], Metallic=0.0, Roughness=0.25, Normal=m_normal)

    # ---- layers as closures: metal, sealant on it, then dirt over that, then soot over all
    shader = g.mix_shader(seal_cov, metal, seal_bsdf, 1350, 0)
    shader = g.mix_shader(dirt, shader, dirt_bsdf, 1500, 0)
    shader = g.mix_shader(soot, shader, soot_bsdf, 1750, 0)
    g.feed(go.inputs["Shader"], shader)
    return ng


def metal_material(key: str) -> bpy.types.Material:
    """Material for one metal: an instance of the shared group with that metal's values."""
    return finish_material(key, METALS[key])


def paint_material(key: str, rgb) -> bpy.types.Material:
    """Tip paint: also an instance of the shared group, so it takes dirt and wear the same way."""
    return finish_material(f"paint {key}", paint(rgb))


def finish_material(key: str, p: Metal) -> bpy.types.Material:
    existing = bpy.data.materials.get(key)
    if existing:
        return existing
    mat = _new(key)
    g = _G(mat.node_tree)
    grp = g.node("ShaderNodeGroup", 0, 0)
    grp.node_tree = metal_group()
    values = {
        "Base Color": (*p.base, 1.0),
        "Edge Tint": (*p.edge, 1.0),
        "Metallic": p.metallic,
        "Roughness": p.roughness,
        "Roughness Variation": p.roughness_var,
        "Tarnish Color": (*p.tarnish, 1.0),
        "Tarnish": p.tarnish_amt,
        "Oxide Film (nm)": p.film_nm,
        "Drawing Marks": p.lines,
        "Specks": p.specks,
        "Micro Dents": p.dimples,
        "Annealing": 1.0 if p.anneal else 0.0,
    }
    for name, value in values.items():
        grp.inputs[name].default_value = value
    out = g.node("ShaderNodeOutputMaterial", 300, 0)
    g.feed(out.inputs["Surface"], grp.outputs["Shader"])
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
