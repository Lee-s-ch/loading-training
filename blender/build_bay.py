# Builds the static loading-bay scenery (island, piping, valves, maintenance stair/platform, bay frame)
# at the same coordinates as preview/index.html. Three.js (x, y, z) -> Blender (x, -z, y).
# Run: blender -b -P blender/build_bay.py -- --render out_dir   (preview images only)
import bpy, bmesh, math, sys, os
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "blender", "assets")
TEX = os.path.join(ROOT, "tex")
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

def B(x, y, z): return Vector((x, -z, y))

def srgb(h):
    c = [((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255]
    return [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c] + [1]

# ---------- scene ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
scn.unit_settings.system = "METRIC"
COL = bpy.data.collections.new("bay_static"); scn.collection.children.link(COL)
CTX = bpy.data.collections.new("context_only"); scn.collection.children.link(CTX)

# ---------- materials ----------
def node_mat(name, color, rough=0.6, metal=0.0, maps=None, alpha_img=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = srgb(color)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if maps:
        for key, (fn, scale) in maps.items():
            p = os.path.join(TEX, fn)
            if not os.path.exists(p): continue
            img = bpy.data.images.load(p); img.colorspace_settings.name = "Non-Color"
            tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = (scale, scale, scale)
            it = nt.nodes.new("ShaderNodeTexImage"); it.image = img
            nt.links.new(tc.outputs["UV"], mp.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], it.inputs["Vector"])
            if key == "normal":
                nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = 0.8
                nt.links.new(it.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
            elif key == "rough":
                mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["To Min"].default_value = rough * 0.75; mr.inputs["To Max"].default_value = min(1, rough * 1.15)
                nt.links.new(it.outputs["Color"], mr.inputs["Value"]); nt.links.new(mr.outputs["Result"], bsdf.inputs["Roughness"])
    if alpha_img:
        it = nt.nodes.new("ShaderNodeTexImage"); it.image = alpha_img
        tc = nt.nodes.new("ShaderNodeTexCoord"); nt.links.new(tc.outputs["UV"], it.inputs["Vector"])
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.inputs["Factor"].default_value = 1
        mix.inputs[6].default_value = srgb(color)
        nt.links.new(it.outputs["Color"], mix.inputs[7]); nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        rnd = nt.nodes.new("ShaderNodeMath"); rnd.operation = "ROUND"
        nt.links.new(it.outputs["Alpha"], rnd.inputs[0]); nt.links.new(rnd.outputs[0], bsdf.inputs["Alpha"])
        try: m.surface_render_method = "DITHERED"
        except Exception: pass
    return m

def grating_image(name="grating", n=256):
    img = bpy.data.images.new(name, n, n, alpha=True)
    px = [0.0] * (n * n * 4)
    for y in range(n):
        for x in range(n):
            bar = (y % 32) < 5 or (x % 64) < 4          # bearing bars every 32 px, cross bars every 64 px
            v = 0.82 + 0.18 * (((x * 7 + y * 13) % 17) / 17) if bar else 0.0
            i = (y * n + x) * 4; px[i:i + 4] = [v, v, v, 1.0 if bar else 0.0]
    img.pixels = px; img.pack(); return img

GRATE = grating_image()
MAT = {
    "frame": node_mat("frame_steel", 0xa9b0ad, 0.55, 0.3),
    "yellow": node_mat("safety_yellow", 0xe5b824, 0.45),
    "pipe": node_mat("pipe_white", 0xeceeea, 0.45),
    "island": node_mat("island_paint", 0x79b8a0, 0.85, maps={"normal": ("painted_nor_gl.jpg", 0.5), "rough": ("painted_rough.jpg", 0.5)}),
    "lane": node_mat("lane_concrete", 0xdcdcd4, 0.9, maps={"normal": ("concrete_nor_gl.jpg", 0.5)}),
    "grate": node_mat("galv_grating", 0x9aa39f, 0.5, 0.65, alpha_img=GRATE),
    "galv": node_mat("galv_steel", 0x9aa39f, 0.5, 0.6),
    "valve": node_mat("valve_body", 0x4a504d, 0.5, 0.5),
    "wheel": node_mat("handwheel", 0x8a5a3c, 0.5, 0.2),
    "dark": node_mat("trench", 0x2a2d2c, 0.8),
    "ground": node_mat("ground_concrete", 0x87847b, 0.95, maps={"normal": ("concrete_nor_gl.jpg", 0.2), "rough": ("concrete_rough.jpg", 0.2)}),
}

# ---------- primitives (sizes and positions in Three.js terms) ----------
def finish(o, mat, bevel=0.0, smooth=False, col=COL):
    for c in o.users_collection: c.objects.unlink(o)
    col.objects.link(o)
    o.data.materials.append(mat)
    if bevel:
        bv = o.modifiers.new("bevel", "BEVEL"); bv.width = bevel; bv.segments = 2; bv.limit_method = "ANGLE"
        o.modifiers.new("wn", "WEIGHTED_NORMAL").keep_sharp = True
    if smooth or bevel:
        for p in o.data.polygons: p.use_smooth = True
    return o

def box(w, h, d, mat, pos, rz=0.0, bevel=0.012, col=COL):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*pos))
    o = bpy.context.object; o.scale = (w, d, h); o.rotation_euler = (0, -rz, 0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(o, mat, bevel, col=col)

def cyl(r, h, mat, pos, axis="y", rz=0.0, seg=24, col=COL):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=seg, location=B(*pos))
    o = bpy.context.object
    if axis == "x": o.rotation_euler = (0, math.pi / 2, 0)
    elif axis == "z": o.rotation_euler = (math.pi / 2, 0, 0)
    else: o.rotation_euler = (0, -rz, 0)
    return finish(o, mat, smooth=True, col=col)

def torus(R, r, mat, pos, axis="y"):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=32, minor_segments=10, location=B(*pos))
    o = bpy.context.object
    if axis == "z": o.rotation_euler = (math.pi / 2, 0, 0)
    return finish(o, mat, smooth=True)

def hbeam(L, H, W, mat, pos, along="y", tw=0.012, tf=0.016):
    """H-section steel: two flanges + web. 'along' is the Three.js axis of the member."""
    x, y, z = pos
    if along == "y":
        for dz in (-H / 2 + tf / 2, H / 2 - tf / 2): box(W, L, tf, mat, (x, y, z + dz), bevel=0.004)
        box(tw, L, H - 2 * tf, mat, (x, y, z), bevel=0.003)
    elif along == "x":
        for dy in (-H / 2 + tf / 2, H / 2 - tf / 2): box(L, tf, W, mat, (x, y + dy, z), bevel=0.004)
        box(L, H - 2 * tf, tw, mat, (x, y, z), bevel=0.003)
    else:
        for dy in (-H / 2 + tf / 2, H / 2 - tf / 2): box(W, tf, L, mat, (x, y + dy, z), bevel=0.004)
        box(tw, H - 2 * tf, L, mat, (x, y, z), bevel=0.003)

def gate_valve(x, z):
    """branch off the header (z -4.3) to a flanged gate valve with a spoked handwheel at (x, ~1.0, z)."""
    cyl(0.07, abs(-4.3 - z) + 0.05, MAT["pipe"], (x, 0.55, (-4.3 + z) / 2), axis="z", seg=20)
    cyl(0.07, 0.45, MAT["pipe"], (x, 0.32, z), seg=20)                 # down into the island
    for y in (0.53, 0.73): cyl(0.12, 0.03, MAT["valve"], (x, y, z), seg=24)  # flanges
    b = cyl(0.1, 0.18, MAT["valve"], (x, 0.63, z), seg=24); b.scale = (1, 0.75, 1)
    cyl(0.05, 0.2, MAT["valve"], (x, 0.84, z), seg=16)                  # bonnet
    cyl(0.016, 0.22, MAT["galv"], (x, 1.0, z), seg=10)                  # stem
    torus(0.16, 0.018, MAT["wheel"], (x, 1.0, z))
    for a in (0, math.pi / 3, 2 * math.pi / 3):
        s = box(0.3, 0.016, 0.016, MAT["wheel"], (x, 1.0, z), bevel=0.0); s.rotation_euler = (0, 0, a)
    cyl(0.03, 0.03, MAT["wheel"], (x, 1.0, z), seg=12)

# ---------- ground-level ----------
box(14.5, 0.04, 1.5, MAT["lane"], (-0.6, 0.02, -2.2), bevel=0.006)
box(16.6, 0.16, 1.9, MAT["island"], (0.45, 0.08, -3.9), bevel=0.02)
box(14.5, 0.02, 0.26, MAT["dark"], (-0.6, 0.005, -1.42), bevel=0.0)           # trench
g = box(14.4, 0.012, 0.22, MAT["grate"], (-0.6, 0.03, -1.42), bevel=0.0)    # trench cover grating
for x in (-7.85, 7.25):
    box(0.02, 0.03, 0.26, MAT["galv"], (x, 0.025, -1.42), bevel=0.0)

# ---------- bay frame: H-section columns and beams ----------
for z in (-3.3, 3.3):
    for x in (-6.6, 5.6):
        hbeam(6.5, 0.28, 0.28, MAT["frame"], (x, 3.25, z), "y")
        box(0.45, 0.02, 0.45, MAT["frame"], (x, 0.17, z), bevel=0.004)     # base plate
        for dx in (-0.16, 0.16):
            for dz in (-0.16, 0.16): cyl(0.018, 0.06, MAT["galv"], (x + dx, 0.19, z + dz), seg=6)
    hbeam(12.5, 0.24, 0.2, MAT["frame"], (-0.5, 6.4, z), "x")
for x in (-6.6, -0.5, 5.6):
    hbeam(6.8, 0.24, 0.2, MAT["frame"], (x, 6.4, 0), "z")

# ---------- island piping ----------
cyl(0.13, 9, MAT["pipe"], (0.4, 0.55, -4.3), axis="x", seg=28)
for x in (-4.1, -1.1, 1.9, 4.9):
    cyl(0.16, 0.035, MAT["pipe"], (x, 0.55, -4.3), axis="x", seg=28)        # flange pairs
    cyl(0.16, 0.035, MAT["pipe"], (x + 0.04, 0.55, -4.3), axis="x", seg=28)
for x in (-3.6, -0.6, 2.2, 4.0):                                             # pipe saddles
    box(0.08, 0.38, 0.3, MAT["frame"], (x, 0.35, -4.3), bevel=0.005)
for x in (-3.2, 2.6, 4.4): gate_valve(x, -3.9)

# ---------- maintenance platform and stair ----------
box(7.2, 0.035, 1.1, MAT["grate"], (1.0, 3.0, -4.25), bevel=0.0)
for z in (-4.78, -3.72):
    box(7.2, 0.16, 0.08, MAT["frame"], (1.0, 2.89, z))                        # platform beam
    box(7.2, 0.12, 0.012, MAT["yellow"], (1.0, 3.09, z), bevel=0.003)        # toe board
    cyl(0.025, 7.2, MAT["yellow"], (1.0, 4.05, z), axis="x", seg=14)         # top rail
    cyl(0.02, 7.2, MAT["yellow"], (1.0, 3.55, z), axis="x", seg=12)          # mid rail
    for x in [-2.6 + 1.2 * i for i in range(7)]: cyl(0.022, 1.05, MAT["yellow"], (x, 3.53, z), seg=12)
for x in (-2.5, 1.0, 4.5):
    for z in (-4.75, -3.75): hbeam(3.0, 0.1, 0.1, MAT["frame"], (x, 1.5, z), "y", tw=0.008, tf=0.01)
L, ang = math.hypot(3.4, 3.0), math.atan2(3.0, 3.4)
for z in (-4.72, -3.78):
    box(L, 0.18, 0.012, MAT["frame"], (-4.3, 1.5, z), rz=ang, bevel=0.003)   # channel stringer
    for dz in (-0.03, 0.03):
        box(L, 0.012, 0.06, MAT["frame"], (-4.3 - 0.09 * math.sin(ang), 1.5 + 0.09 * math.cos(ang), z + dz * (1 if z > -4.25 else -1)), rz=ang, bevel=0.0)
    h = cyl(0.022, L, MAT["yellow"], (-4.3, 2.5, z), rz=ang - math.pi / 2, seg=12)
    m = cyl(0.018, L, MAT["yellow"], (-4.3, 2.0, z), rz=ang - math.pi / 2, seg=12)
    cyl(0.03, 1.0, MAT["yellow"], (-6.0, 0.5, z), seg=12)                    # newel post
for i in range(1, 12):
    x, y = -6.0 + 3.4 * i / 12, 3.0 * i / 12
    box(0.26, 0.03, 0.9, MAT["grate"], (x, y, -4.25), bevel=0.0)
    box(0.03, 0.035, 0.9, MAT["yellow"], (x + 0.13, y + 0.002, -4.25), bevel=0.004)  # yellow nosing

# ---------- context for the preview only (not exported) ----------
def ctx_plane():
    bpy.ops.mesh.primitive_plane_add(size=120, location=(0, 0, 0))
    o = bpy.context.object
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.uv.cube_project(cube_size=1.0); bpy.ops.object.mode_set(mode="OBJECT")
    return finish(o, MAT["ground"], col=CTX)
ctx_plane()

# world-scale UVs for every textured object
for o in COL.objects:
    if o.data.materials and o.data.materials[0].name in ("island_paint", "lane_concrete", "galv_grating"):
        bpy.context.view_layer.objects.active = o; o.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.cube_project(cube_size=1.0 if o.data.materials[0].name != "galv_grating" else 0.5)
        bpy.ops.object.mode_set(mode="OBJECT"); o.select_set(False)

# ---------- light: overcast HDRI + the page's sun ----------
w = bpy.data.worlds.new("sky"); scn.world = w; w.use_nodes = True
hdr = os.path.join(ASSETS, "overcast_industrial_courtyard_2k.hdr")
if os.path.exists(hdr):
    env = w.node_tree.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(hdr)
    w.node_tree.links.new(env.outputs["Color"], w.node_tree.nodes["Background"].inputs["Color"])
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scn.collection.objects.link(sun)
sun.data.energy = 3.2; sun.data.angle = math.radians(2.5); sun.data.color = (1, 0.95, 0.88)
d = (Vector((0, 0, 0)) - B(-6, 15, -10)).normalized()
sun.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()

# ---------- preview renders ----------
def shot(name, pos, target, out_dir, fov=42):
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name)); scn.collection.objects.link(cam)
    cam.location = B(*pos); cam.data.sensor_fit = "VERTICAL"; cam.data.angle_y = math.radians(fov); cam.data.clip_end = 400
    cam.rotation_euler = (B(*target) - B(*pos)).to_track_quat("-Z", "Y").to_euler()
    scn.camera = cam; scn.render.filepath = os.path.join(out_dir, name + ".png")
    bpy.ops.render.render(write_still=True)

if "--render" in args:
    out = args[args.index("--render") + 1]; os.makedirs(out, exist_ok=True)
    r = scn.render; r.resolution_x, r.resolution_y = 1280, 720
    r.engine = "CYCLES"; scn.cycles.samples = 96; scn.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences; prefs.compute_device_type = "CUDA"; prefs.get_devices()
        for dv in prefs.devices: dv.use = True
        scn.cycles.device = "GPU"
    except Exception as e: print("GPU unavailable:", e)
    scn.view_settings.view_transform = "AgX"
    shot("after_all", (11.5, 7.2, -11.0), (1.0, 2.3, -0.6), out)
    shot("after_close", (-1.2, 1.9, -0.6), (-3.6, 1.0, -4.1), out, fov=50)
