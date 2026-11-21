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
* soot: matte carbon inside fired cases (heaviest at the floor and lower walls, thinning
  toward the mouth) and blow-by streaks on the neck, folded into the metal layer
* coat: a thin tinted clear coat over the metal (``Coat``): the polymer or lacquer on
  steel cases. Steel shows through it, it has its own orange-peel and mottling, and
  scratches cut through it to bare steel
* factory toning: small dark water spots and stains that come with age, so even boxed new
  ammo isn't mirror-bright (``Age Response`` scales how much a metal shows its age:
  nickel plating barely tarnishes)

The three layers are complete BSDFs mixed as closures, like Unreal Substrate slabs: masks
only set coverage, so mask edges never produce half-metallic, pale-looking brass.

* sealant layer: primer lacquer (purple, red, blue, ...) in a ring at the cup's edge, sometimes
  run over part of the face

Per-copy drivers live in the object colour (R dirt, G soot inside, B soot outside,
A annealing amount) and in object properties: ``gf_age`` (tarnish spreads, streaks and
darkens), ``gf_wear`` (scratches along the case, hairlines every which way, rubbed edges),
``gf_grime`` (a thin film of old grease, oxidation mottling, thousands of micro-dings),
``gf_iris`` (heat-tint annealing), and on primers ``gf_seal`` (sealant colour, black for
none) and ``gf_smear``. The baked ``edge`` attribute marks convex edges (rims, mouths,
letter lips), which wear bright and collect the most dings. Texture space is object space in millimetres,
offset by the object's random value, so every copy gets its own pattern.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import bpy

GROUP = "GF Metal"
GROUP_VERSION = 4  # bump when the group changes: files with an older group get it rebuilt


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
    coat: float = 0.0  # thin clear coat over the metal (polymer, lacquer), 0-1
    coat_roughness: float = 0.4
    coat_tint: tuple[float, float, float] = (1.0, 1.0, 1.0)  # absorption: darkens what shows through
    age_response: float = 1.0  # how strongly the copy's age shows (tarnish, dulling, spots)


METALS: dict[str, Metal] = {
    "brass": Metal((0.88, 0.70, 0.34), (1.00, 0.94, 0.80), 0.15, tarnish=(0.60, 0.44, 0.20), tarnish_amt=0.22, film_nm=40, lines=0.3, specks=0.4, anneal=True),
    # drawn FMJ jackets: satin, tarnish from bright to dull
    "gilding-metal": Metal((0.93, 0.58, 0.40), (1.00, 0.86, 0.76), 0.20, tarnish=(0.55, 0.30, 0.20), tarnish_amt=0.18, film_nm=40, lines=0.3, specks=0.3, dimples=0.4),
    # plated bullets: matte from the plating bath, soft over lead, quick to oxidize
    "copper": Metal((0.955, 0.637, 0.538), (1.00, 0.86, 0.78), 0.34, roughness_var=0.06, tarnish=(0.40, 0.21, 0.14), tarnish_amt=0.40, film_nm=70, lines=0.0, specks=0.5, dimples=0.7),
    "lead": Metal((0.28, 0.285, 0.30), (0.70, 0.70, 0.72), 0.6, roughness_var=0.08, tarnish=(0.20, 0.20, 0.21), tarnish_amt=0.5, film_nm=0, lines=0.0, specks=0.3, dimples=0.8, metallic=0.75),
    # bright nickel plating: very shiny, but satin rather than chrome; hardly tarnishes
    "nickel": Metal((0.68, 0.65, 0.59), (0.92, 0.91, 0.89), 0.10, roughness_var=0.03, tarnish=(0.55, 0.52, 0.47), tarnish_amt=0.04, film_nm=10, lines=0.25, specks=0.2, dimples=0.4, age_response=0.35),
    "steel": Metal((0.56, 0.57, 0.58), (0.85, 0.86, 0.88), 0.25, tarnish=(0.35, 0.25, 0.18), tarnish_amt=0.3, film_nm=40),
    "aluminum": Metal((0.91, 0.92, 0.92), (0.97, 0.97, 0.98), 0.32, tarnish=(0.75, 0.76, 0.77), tarnish_amt=0.3, film_nm=0),
    # steel cases: phosphated steel under a thin, dull grey polymer coat, or under a glossier
    # olive lacquer. The tint is the coat's absorption; the steel's sheen shows through it.
    "steel-polymer": Metal((0.52, 0.53, 0.54), (0.80, 0.81, 0.83), 0.50, roughness_var=0.06, tarnish=(0.22, 0.15, 0.10), tarnish_amt=0.05, film_nm=0, lines=0.1, specks=0.5, dimples=0.4, coat=1.0, coat_roughness=0.38, coat_tint=(0.14, 0.145, 0.145), age_response=0.6),
    "steel-lacquer": Metal((0.52, 0.53, 0.54), (0.80, 0.81, 0.83), 0.38, roughness_var=0.05, tarnish=(0.22, 0.15, 0.10), tarnish_amt=0.08, film_nm=0, lines=0.1, specks=0.4, dimples=0.4, coat=1.0, coat_roughness=0.22, coat_tint=(0.19, 0.18, 0.10), age_response=0.7),
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
    ("Coat", "NodeSocketFloat", 0.0),
    ("Coat Roughness", "NodeSocketFloat", 0.4),
    ("Coat Tint", "NodeSocketColor", (1.0, 1.0, 1.0, 1.0)),
    ("Age Response", "NodeSocketFloat", 1.0),
]

ANNEAL_FRINGE = (0.36, 0.24, 0.10, 1.0)  # darkened gold where the heat faded out
ANNEAL_CORE = (0.15, 0.095, 0.045, 1.0)  # dark bronze-brown on the neck, where it was hottest
# heat tint (temper colours of the oxide), from the cool end of the band to the hot neck
HEAT_TINT = [
    (0.22, (0.86, 0.64, 0.26, 1.0)),  # straw
    (0.42, (0.74, 0.42, 0.17, 1.0)),  # gold to bronze
    (0.60, (0.56, 0.24, 0.24, 1.0)),  # copper-red
    (0.76, (0.42, 0.22, 0.36, 1.0)),  # purple
    (1.00, (0.26, 0.18, 0.15, 1.0)),  # dark bronze with a hint of violet
]
METALS_BRASS_BASE = (0.88, 0.70, 0.34)
SOIL_DARK = (0.025, 0.019, 0.013, 1.0)
SOIL_LIGHT = (0.085, 0.064, 0.042, 1.0)
SOOT = (0.014, 0.013, 0.012, 1.0)
GREASE_TINT = (0.80, 0.70, 0.50, 1.0)  # an old film of manufacturing grease: warm, a little dark


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
    """The shared ``GF Metal`` node group (built once per file, rebuilt in place if outdated)."""
    ng = bpy.data.node_groups.get(GROUP)
    if ng and ng.get("gf_version") == GROUP_VERSION:
        return ng
    if ng:  # an older group: rebuild it in place, so every material using it follows
        ng.nodes.clear()
        ng.interface.clear()
    else:
        ng = bpy.data.node_groups.new(GROUP, "ShaderNodeTree")
    ng["gf_version"] = GROUP_VERSION
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
    # Noise nodes are the shader's bulk, and a group too big for the GPU fails to compile
    # (EEVEE then drops parts of it without a word), so every spare output is reused.
    lo_f, lo_r, lo_g, lo_b = g.noise_rgb(pmm, w, 0.25, 2.0, -1400, 400)  # oxidation, tarnish, drift, anneal streaks
    _, hi_r, hi_g, hi_b = g.noise_rgb(pmm, w, 3.0, 2.0, -1400, 0)  # fine roughness, specks, water spots
    stretch = g.node("ShaderNodeVectorMath", -1600, -550, operation="MULTIPLY")
    g.feed(stretch.inputs[0], pmm)
    stretch.inputs[1].default_value = (6.0, 6.0, 0.08)
    lines_fac, _, _, _ = g.noise_rgb(stretch.outputs[0], w, 1.0, 1.0, -1400, -550)  # drawing marks along the axis
    vor = g.node("ShaderNodeTexVoronoi", -1400, -850, voronoi_dimensions="3D", feature="F1")
    g.feed(vor.inputs["Vector"], g.node("ShaderNodeVectorMath", -1550, -850, operation="ADD", inputs={0: pmm, 1: w}).outputs[0])
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
    # per-copy object properties (EEVEE allows 8 such uniforms per material; keep it at 6)
    age = g.math("MULTIPLY", g.attr("gf_age", "OBJECT", x=-1800, y=650), gi["Age Response"], -1600, 650, clamp=True)  # tarnish with age, 0-1
    wear = g.attr("gf_wear", "OBJECT", x=-1600, y=-1250)  # scratches and scuffs, 0-1
    grime_amt = g.attr("gf_grime", "OBJECT", x=-1800, y=-1650)  # grease film, oxidation, micro-dings, 0-1
    edge = g.attr("edge", x=-1800, y=-1800)  # convex edges, baked per mesh
    edge_w = g.math("MULTIPLY", edge, g.madd(g.math("MAXIMUM", wear, grime_amt, -1600, -1850), 0.7, 0.3, -1450, -1850), -1300, -1800, clamp=True)

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

    # ---- hairline scratches every which way (boxes, magazines, handling), more on the edges
    ms_amt = g.madd(grime_amt, 0.6, g.math("MULTIPLY", wear, 0.8, -1200, -2000), -1100, -2000)
    ms_amt = g.madd(edge_w, 0.6, ms_amt, -1000, -2000, clamp=True)
    hair = None
    _, mk_r, mk_g, _ = g.noise_rgb(pmm, g.math("ADD", w, 50.0, -1600, -2050), 1.4, 0.0, -1300, -2050)
    for i, (rot, mf) in enumerate((((0.0, 1.25, 0.4), mk_r), ((1.1, 0.35, 2.1), mk_g))):
        y = -2150 - 220 * i
        vr = g.node("ShaderNodeVectorRotate", -1600, y, rotation_type="EULER_XYZ")
        g.feed(vr.inputs["Vector"], pmm)
        vr.inputs["Rotation"].default_value = rot
        sq = g.node("ShaderNodeVectorMath", -1450, y, operation="MULTIPLY")
        g.feed(sq.inputs[0], vr.outputs[0])
        sq.inputs[1].default_value = (0.4, 18.0, 18.0)  # hairlines along the rotated x
        hf, _, _, _ = g.noise_rgb(sq.outputs[0], g.math("ADD", w, 40.0 + i, -1600, y - 80), 1.0, 0.0, -1300, y)
        hl = g.map(g.math("ABSOLUTE", g.math("SUBTRACT", hf, 0.5, -1100, y), 0.0, -1000, y), 0.0, 0.009, 1.0, 0.0, x=-900, y=y)
        m_lo = g.madd(ms_amt, -0.20, 0.63, -1100, y - 100)
        hm = g.map(mf, m_lo, g.math("ADD", m_lo, 0.04, -1000, y - 140), x=-900, y=y - 100)
        h = g.math("MULTIPLY", hl, hm, -800, y)
        hair = h if hair is None else g.math("MAXIMUM", hair, h, -700, y)
    hair = g.math("MULTIPLY", hair, ms_amt, -600, -2200, clamp=True)
    scratch = g.math("MAXIMUM", scratch, g.math("MULTIPLY", hair, 0.7, -500, -2200), -450, -1200)
    unscratched = g.math("SUBTRACT", 1.0, scratch, -550, -1200)

    # ---- micro-dings: thousands of tiny pits from tumbling and bulk packing, densest on the
    # edges; each one catches a little grime
    mv = g.node("ShaderNodeTexVoronoi", -1400, -2900, voronoi_dimensions="3D", feature="F1")
    g.feed(mv.inputs["Vector"], g.node("ShaderNodeVectorMath", -1550, -2900, operation="ADD", inputs={0: pmm, 1: g.math("ADD", w, 60.0, -1650, -2950)}).outputs[0])
    mv.inputs["Scale"].default_value = 4.5
    mcell = g.node("ShaderNodeSeparateColor", -1200, -3000)
    g.feed(mcell.inputs[0], mv.outputs["Color"])
    density = g.madd(wear, 0.10, 0.03, -1200, -3100)
    density = g.madd(grime_amt, 0.35, density, -1100, -3100)
    density = g.madd(edge_w, 0.35, density, -1000, -3100, clamp=True)
    d_lo = g.math("SUBTRACT", 1.0, density, -900, -3100)
    mpick = g.map(mcell.outputs[0], d_lo, g.math("ADD", d_lo, 0.01, -850, -3150), x=-750, y=-3050)
    mbowl = g.map(mv.outputs["Distance"], 0.0, 0.32, 1.0, 0.0, x=-750, y=-2900, smooth=True)
    mding = g.math("MULTIPLY", mbowl, mpick, -600, -2950)

    tarnish = g.math("MULTIPLY", g.math("MULTIPLY", g.math("MAXIMUM", blot, streaks, -800, 550), t_amt, -700, 550), unscratched, -600, 550)
    rubbed = g.madd(edge_w, -0.75, 1.0, -700, 450)  # handled edges are rubbed bright
    tarnish = g.math("MULTIPLY", tarnish, rubbed, -500, 550)

    # ---- factory toning: small dark water spots and stains, more and more of them with age
    spot_fac = hi_b
    spot_lo = g.madd(grime_amt, -0.04, g.madd(age, -0.06, 0.715, -1300, 250), -1200, 250)
    spots = g.map(spot_fac, spot_lo, g.math("ADD", spot_lo, 0.02, -1100, 200), x=-1000, y=250, smooth=True)
    spots = g.math("MULTIPLY", g.math("MULTIPLY", spots, g.map(age, 0.03, 0.3, x=-1000, y=150), -850, 250), unscratched, -700, 250)

    # ---- metal layer
    rv = gi["Roughness Variation"]
    rough = g.madd(fine, g.math("MULTIPLY", rv, 0.35, -600, 150), gi["Roughness"], -400, 0)
    rough = g.madd(drift, g.math("MULTIPLY", rv, 0.5, -400, 150), rough, -250, 0)
    rough = g.madd(lines, 0.04, rough, -100, 0)
    rough = g.madd(specks, 0.10, rough, 50, 0)
    rough = g.madd(tarnish, 0.10, rough, 200, 0)
    rough = g.madd(spots, 0.12, rough, 240, 0)
    rough = g.madd(age, 0.10, rough, 275, 0)  # old brass is dull all over
    rough = g.madd(scratch, 0.30, rough, 300, -100)
    rough = g.madd(cavity, 0.25, rough, 350, 0)
    rough = g.madd(dirt_amt, 0.2, rough, 450, 0)  # brass that has lain in the dirt is dull
    rough = g.madd(grime_amt, 0.05, rough, 475, 0)  # handled, greasy brass is a little hazy
    rough = g.madd(mding, 0.25, rough, 500, 0)
    rough = g.madd(edge_w, 0.05, rough, 525, 0)
    rough = g.madd(g.math("SUBTRACT", rnd, 0.5, -400, -250), 0.04, rough, 550, 0, clamp=True)

    dark_t = g.node("ShaderNodeVectorMath", -600, 800, operation="SCALE")
    g.feed(dark_t.inputs[0], gi["Tarnish Color"])
    _sock(dark_t.inputs, "Scale").default_value = 0.30
    t_colour = g.mix(g.math("MULTIPLY", age, 0.9, -600, 950), gi["Tarnish Color"], dark_t.outputs[0], -450, 850)
    colour = g.mix(g.math("MULTIPLY", tarnish, 0.95, -600, 650), gi["Base Color"], t_colour, -300, 650)
    colour = g.mix(g.math("MULTIPLY", g.math("MULTIPLY", spots, 0.65, -300, 500), rubbed, -250, 500), colour, dark_t.outputs[0], -150, 600)
    # oxidation: the brass goes darker in soft, uneven patches (not on rubbed edges)
    ox_fac = lo_f
    ox_amt = g.madd(grime_amt, 0.40, g.madd(age, 0.15, 0.10, -900, 100), -800, 100)
    ox = g.math("MULTIPLY", g.math("MULTIPLY", g.map(ox_fac, 0.35, 0.65, x=-900, y=150), ox_amt, -700, 150), rubbed, -600, 150)
    ox_dark = g.node("ShaderNodeVectorMath", -400, 250, operation="SCALE")
    g.feed(ox_dark.inputs[0], colour)
    _sock(ox_dark.inputs, "Scale").default_value = 0.55
    colour = g.mix(ox, colour, ox_dark.outputs[0], -250, 300)
    tone = g.node("ShaderNodeVectorMath", -150, 300, operation="SCALE")  # lots differ a little in tone
    g.feed(tone.inputs[0], colour)
    g.feed(_sock(tone.inputs, "Scale"), g.madd(rnd, 0.10, 0.93, -300, 200))
    colour = tone.outputs[0]
    colour = g.mix(g.math("MULTIPLY", mding, 0.6, -150, 450), colour, dark_t.outputs[0], -50, 450)
    film = g.math("MULTIPLY", tarnish, gi["Oxide Film (nm)"], -400, 850)
    # annealing stain: dark bronze on the neck fading through darkened gold into the body
    a_band = g.attr("anneal", x=-1200, y=1150)
    anneal = g.math("MULTIPLY", g.math("MULTIPLY", a_band, anneal_amt, -1000, 1150), gi["Annealing"], -850, 1150)
    anneal = g.math("MULTIPLY", anneal, g.map(lo_b, 0.2, 0.8, 0.8, 1.2, x=-1000, y=1350), -700, 1150, clamp=True)
    a_colour = g.mix(g.map(a_band, 0.3, 1.0, smooth=True, x=-700, y=1300), ANNEAL_FRINGE, ANNEAL_CORE, -550, 1300)
    # heat tint (gf_iris): the oxide's temper colours instead of a stain, straw and gold low on
    # the shoulder through bronze and purple to dark violet-bronze on the neck. Painted
    # from a ramp rather than thin-film interference, which EEVEE doesn't draw.
    iris = g.attr("gf_iris", "OBJECT", x=-1200, y=1450)
    stain = g.madd(iris, -0.7, 1.0, -700, 1450)
    colour = g.mix(g.math("MULTIPLY", g.math("MULTIPLY", anneal, 1.0, -550, 1150), stain, -400, 1150), colour, a_colour, -200, 950)
    heat = g.node("ShaderNodeValToRGB", -600, 1650)
    g.feed(heat.inputs["Fac"], g.madd(g.math("SUBTRACT", lo_g, 0.5, -900, 1700), 0.25, a_band, -750, 1650, clamp=True))
    els = heat.color_ramp.elements
    els[0].position, els[0].color = 0.0, (*METALS_BRASS_BASE, 1.0)
    els[1].position, els[1].color = 1.0, HEAT_TINT[-1][1]
    for pos, rgba in HEAT_TINT[:-1]:
        e = els.new(pos)
        e.color = rgba
    colour = g.mix(g.math("MULTIPLY", g.math("MULTIPLY", anneal, iris, -450, 1550), 0.65, -300, 1550), colour, heat.outputs["Color"], -100, 1100)  # faint: the brass still shows
    rough = g.madd(anneal, 0.10, rough, 600, 0, clamp=True)  # the oxide is satin
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
    m_height = g.madd(scratch, -1.2, m_height, 350, -700)
    m_height = g.madd(mding, -0.9, m_height, 380, -750)
    m_normal = g.node("ShaderNodeBump", 450, -450, inputs={"Strength": 0.2, "Distance": 0.00001, "Height": m_height}).outputs["Normal"]

    # ---- coat: thin polymer or lacquer over the metal; uneven, orange-peeled, worn through.
    # Bare metal gets a thin film of old grease instead, as much as the copy's grime.
    grease = g.math("MULTIPLY", grime_amt, g.math("SUBTRACT", 1.0, gi["Coat"], 400, 650), 500, 650)
    grease = g.math("MULTIPLY", grease, g.madd(edge_w, -0.5, 1.0, 400, 600), 550, 650)
    coat_w = g.madd(grease, 0.35, g.math("MULTIPLY", gi["Coat"], unscratched, 600, 800), 700, 750)
    c_rough = g.madd(fine, 0.05, gi["Coat Roughness"], 450, 1000)
    c_rough = g.madd(specks, 0.2, c_rough, 550, 1000)
    c_rough = g.madd(age, 0.12, c_rough, 650, 1000)
    c_rough = g.madd(dirt_amt, 0.2, c_rough, 750, 1000, clamp=True)
    mottle = g.math("MULTIPLY", g.map(hi_r, 0.3, 0.7, 0.92, 1.08, x=300, y=1200), g.map(lo_b, 0.3, 0.7, 0.93, 1.07, x=300, y=1350), 450, 1250)
    c_tint = g.node("ShaderNodeVectorMath", 600, 1250, operation="SCALE")
    g.feed(c_tint.inputs[0], gi["Coat Tint"])
    g.feed(_sock(c_tint.inputs, "Scale"), mottle)
    c_tint = g.mix(g.math("SUBTRACT", 1.0, gi["Coat"], 650, 1350), c_tint.outputs[0], GREASE_TINT, 750, 1300)
    c_rough = g.madd(g.math("SUBTRACT", 0.30, c_rough, 750, 1100), g.math("SUBTRACT", 1.0, gi["Coat"], 650, 1100), c_rough, 850, 1050)  # grease: 0.30, a thin oily sheen
    c_height = g.madd(specks, 0.6, g.math("MULTIPLY", fine, 0.5, 300, -1100), 450, -1100)
    c_normal = g.node("ShaderNodeBump", 650, -1100, inputs={"Strength": 0.12, "Distance": 0.00001, "Height": c_height}).outputs["Normal"]

    # ---- soot: inside a fired case, heaviest on the floor and lower walls and thinning out
    # toward the mouth (ragged edge), plus blow-by on the neck outside. Folded into the metal
    # BSDF (its colour and edge tint go to carbon black, it goes rough) rather than layered as
    # its own closure: EEVEE evaluates only a few closures per pixel and dropped partial soot.
    zj = g.madd(g.math("SUBTRACT", lo_b, 0.5, -1000, 2650), 0.25, zn, -900, 2700)
    upper = g.madd(g.map(zj, 0.5, 1.0, x=-800, y=2650), -0.45, 1.0, -700, 2650)  # full low down, 0.55 at the mouth
    falloff = g.math("MULTIPLY", upper, g.map(zn, 0.02, 0.2, 1.3, 1.0, x=-800, y=2750), -600, 2700)
    soot_in = g.math("MULTIPLY", g.math("MULTIPLY", interior, soot_in_amt, -800, 2900), falloff, -600, 2850)
    soot_in = g.math("MULTIPLY", soot_in, g.map(lo_b, 0.3, 0.7, 0.8, 1.2, x=-800, y=3050), -450, 2900, clamp=True)
    outside = g.math("SUBTRACT", 1.0, interior, -800, 3200)
    neck = g.map(zn, 0.62, 0.96, x=-800, y=3350, smooth=True)
    streak = g.map(streak_fac, 0.3, 0.7, 0.35, 1.0, x=-800, y=3500)  # broad blow-by streaks along the neck
    soot_out = g.math("MULTIPLY", g.math("MULTIPLY", outside, neck, -600, 3250), g.math("MULTIPLY", soot_out_amt, streak, -600, 3600), -450, 3400, clamp=True)
    soot = g.map(g.math("ADD", soot_in, soot_out, -300, 3100, clamp=True), 0.05, 0.75, x=-150, y=3100, smooth=True)
    unsooted = g.math("SUBTRACT", 1.0, soot, 850, 300)
    colour = g.mix(soot, colour, SOOT, 900, 450)
    coat_w = g.math("MULTIPLY", coat_w, unsooted, 900, 750)

    metal = g.bsdf(
        1000,
        400,
        Base_Color=colour,
        Metallic=gi["Metallic"],  # soot darkens the metal's colour and edge tint instead: half-metal looks pale
        Roughness=g.madd(g.math("SUBTRACT", 0.9, rough, 850, 150), soot, rough, 900, 150),
        Specular_Tint=g.mix(soot, gi["Edge Tint"], SOOT, 900, -50),
        Thin_Film_Thickness=g.math("MULTIPLY", film, unsooted, 900, -100),  # a high-index film on soot would glow beige
        Thin_Film_IOR=2.0,
        Normal=m_normal,
        Coat_Weight=coat_w,
        Coat_Roughness=c_rough,
        Coat_IOR=1.5,
        Coat_Tint=c_tint,
        Coat_Normal=c_normal,
    )

    # ---- dirt layer: soil, patchy, in recesses first, plus a thin film of dust
    w3 = g.math("ADD", w, 31.0, -1400, 2300)
    soil_fac, soil_r, _, soil_b = g.noise_rgb(pmm, w3, 1.1, 4.0, -1200, 2300)
    lo_cut = g.madd(dirt_amt, -0.6, 1.08, -800, 2450)  # more dirt: lower threshold, wider patches
    patches = g.map(soil_fac, lo_cut, g.math("ADD", lo_cut, 0.12, -800, 2550), x=-600, y=2400, smooth=True)
    dirt = g.madd(cavity, dirt_amt, g.math("MULTIPLY", patches, dirt_amt, -400, 2400), -250, 2350)
    dirt = g.madd(dirt_amt, 0.12, dirt, -100, 2350, clamp=True)
    dirt = g.math("MULTIPLY", dirt, g.madd(scratch, -0.7, 1.0, -100, 2250), 0, 2350)  # scratches cut through it
    dirt = g.math("MULTIPLY", dirt, g.madd(edge_w, -0.6, 1.0, -100, 2200), 100, 2350)  # and edges rub it off
    soil = g.mix(soil_b, SOIL_DARK, SOIL_LIGHT, -400, 2150)
    d_height = g.madd(soil_r, 1.0, g.math("MULTIPLY", dimple, 0.5, 300, -900), 450, -900)
    d_normal = g.node("ShaderNodeBump", 650, -900, inputs={"Strength": 0.6, "Distance": 0.00003, "Height": d_height}).outputs["Normal"]
    soil_rough = g.map(soil_fac, 0.3, 0.7, 0.88, 1.0, x=700, y=-700)
    dirt_bsdf = g.bsdf(1000, -300, Base_Color=soil, Metallic=0.0, Roughness=soil_rough, Specular_IOR_Level=0.2, Normal=d_normal)


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
    g.feed(go.inputs["Shader"], shader)
    return ng


def metal_material(key: str) -> bpy.types.Material:
    """Material for one metal: an instance of the shared group with that metal's values."""
    return finish_material(key, METALS[key])


def paint_material(key: str, rgb) -> bpy.types.Material:
    """Tip paint: also an instance of the shared group, so it takes dirt and wear the same way."""
    return finish_material(f"paint {key}", paint(rgb))


def finish_material(key: str, p: Metal) -> bpy.types.Material:
    """One material per metal. A material from an older version gets this version's values
    once; after that, edits made to it in Blender are kept."""
    group = metal_group()
    mat = bpy.data.materials.get(key)
    if mat and mat.get("gf_version") == GROUP_VERSION:
        return mat
    grp = None
    if mat and mat.node_tree:
        grp = next((n for n in mat.node_tree.nodes if n.type == "GROUP" and n.node_tree == group), None)
    if grp is None:
        mat = mat or _new(key)
        mat.node_tree.nodes.clear()
        g = _G(mat.node_tree)
        grp = g.node("ShaderNodeGroup", 0, 0)
        grp.node_tree = group
        out = g.node("ShaderNodeOutputMaterial", 300, 0)
        g.feed(out.inputs["Surface"], grp.outputs["Shader"])
    mat["gf_version"] = GROUP_VERSION
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
        "Coat": p.coat,
        "Coat Roughness": p.coat_roughness,
        "Coat Tint": (*p.coat_tint, 1.0),
        "Age Response": p.age_response,
    }
    for name, value in values.items():
        grp.inputs[name].default_value = value
    tint = p.coat_tint if p.coat else (1.0, 1.0, 1.0)
    mat.diffuse_color = (*(b * t for b, t in zip(p.base, tint)), 1.0)  # solid-mode viewport colour
    return mat


def label_material() -> bpy.types.Material:
    """Black, matte text for the cartridge labels."""
    mat = bpy.data.materials.get("label")
    if mat:
        return mat
    mat = _new("label")
    g = _G(mat.node_tree)
    bsdf = g.node("ShaderNodeBsdfPrincipled", 0, 0, inputs={"Base Color": (0.0, 0.0, 0.0, 1.0), "Roughness": 0.9})
    out = g.node("ShaderNodeOutputMaterial", 300, 0)
    g.feed(out.inputs["Surface"], bsdf.outputs["BSDF"])
    mat.diffuse_color = (0.0, 0.0, 0.0, 1.0)
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
    ramp.color_ramp.elements[0].color = (0.42, 0.42, 0.43, 1)  # below the horizon: stands in for the lit floor in reflections
    ramp.color_ramp.elements[1].color = (0.70, 0.71, 0.75, 1)
    mid = ramp.color_ramp.elements.new(0.45)
    mid.color = (0.16, 0.16, 0.17, 1)  # a darker band above the horizon gives metals their contrast
    bg = g.node("ShaderNodeBackground", 0, 0, inputs={"Strength": 0.35})
    g.feed(bg.inputs["Color"], ramp.outputs["Color"])
    out = g.node("ShaderNodeOutputWorld", 250, 0)
    g.feed(out.inputs["Surface"], bg.outputs["Background"])
