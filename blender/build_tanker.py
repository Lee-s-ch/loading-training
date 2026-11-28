# Builds the tank lorry in the same local frame as preview/index.html (cab toward +x, then mirrored: world x = 0.6 - x).
# Run: blender -b -P blender/build_tanker.py -- --shots out_dir   (preview images, with the bay as context)
import bpy, bmesh, math, os, sys
from mathutils import Vector

_here = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(_here, "build_bay.py"), encoding="utf-8").read())   # scene, materials, helpers, bay (context)

EXPORT = "--export" in args   # web export: truck-local frame, one wheel template, no grounding box (the page keeps its own)
TCOL = bpy.data.collections.new("tanker"); bpy.context.scene.collection.children.link(TCOL)

def pm(name, color, rough, metal=0.0, coat=0.0, emit=None, aniso=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb(color); b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    if coat: b.inputs["Coat Weight"].default_value = coat; b.inputs["Coat Roughness"].default_value = 0.08
    if aniso: b.inputs["Anisotropic"].default_value = aniso
    if emit: b.inputs["Emission Color"].default_value = srgb(emit[0]); b.inputs["Emission Strength"].default_value = emit[1]
    return m

TM = {
    "tank": pm("tank_stainless", 0xdfe2e3, 0.26, 1.0),   # no anisotropy: without tangents it renders NaN on the web
    "band": pm("tank_band", 0x4b5866, 0.38, 0.2, coat=0.4),
    "stripe": pm("pinstripe", 0xf2b830, 0.4),
    "cab": pm("cab_paint", 0xeef0f1, 0.3, 0.0, coat=1.0),
    "chassis": pm("chassis_black", 0x2b2e2d, 0.55, 0.2),
    "tire": pm("tire_rubber", 0x1b1c1c, 0.88),
    "rim": pm("rim_alloy", 0xc3c8c5, 0.28, 0.9),
    "steel": pm("steel", 0xa6aca9, 0.35, 0.85),
    "chrome": pm("chrome", 0xe6e8e8, 0.08, 1.0),
    "glass": pm("glass_dark", 0x18222a, 0.04, 0.1, coat=1.0),
    "plastic": pm("plastic_dark", 0x2e3231, 0.6),
    "amber": pm("lamp_amber", 0xffa21a, 0.3, emit=(0xff8a00, 3.0)),
    "red": pm("lamp_red", 0xd0221a, 0.3, emit=(0xff1a0a, 2.0)),
    "head": pm("lamp_head", 0xfff6e0, 0.1, emit=(0xfff2d0, 1.5)),
    "green": pm("socket_green", 0x2f9e4f, 0.45),
    "hazard": pm("rear_hazard", 0xf2c230, 0.5),
}

def tbox(w, h, d, mat, pos, rz=0.0, bevel=0.01): return box(w, h, d, mat, pos, rz=rz, bevel=bevel, col=TCOL)
def tcyl(r, h, mat, pos, axis="y", rz=0.0, seg=24): return cyl(r, h, mat, pos, axis=axis, rz=rz, seg=seg, col=TCOL)

def ring_mesh(name, profile, mat_of, seg=72, ys=0.82, cy=2.42):
    """Surface of revolution about the truck's x axis. profile: [(x, r)], cross-section squashed vertically by ys."""
    me = bpy.data.meshes.new(name); bm = bmesh.new(); rings = []
    for x, r in profile:
        ring = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            ring.append(bm.verts.new(B(x, cy + math.sin(a) * r * ys, math.cos(a) * r)))
        rings.append(ring)
    for j in range(len(rings) - 1):
        for i in range(seg):
            f = bm.faces.new((rings[j][i], rings[j][(i + 1) % seg], rings[j + 1][(i + 1) % seg], rings[j + 1][i]))
            f.smooth = True
            c = f.calc_center_median(); f.material_index = mat_of(c)
    for ring, x in ((rings[0], profile[0][0]), (rings[-1], profile[-1][0])):
        if profile[0][1] > 1e-4 or True:
            pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); TCOL.objects.link(o); return o

# ---------- tank barrel with elliptical dished heads, two-tone lower band ----------
R, HD, X0, X1 = 1.15, 0.30, -5.2, 2.4
prof = []
for k in range(12, -1, -1):  # rear head
    t = k / 12; prof.append((X0 - HD * t, R * math.sqrt(max(0.0, 1 - t * t)) + (1e-3 if k == 12 else 0)))
for k in range(1, 40): prof.append((X0 + (X1 - X0) * k / 40, R))
for k in range(0, 13):
    t = k / 12; prof.append((X1 + HD * t, R * math.sqrt(max(0.0, 1 - t * t)) + (1e-3 if k == 12 else 0)))
band_z = 2.42 - 0.943 * 0.42   # Blender z of the band's top edge
tank = ring_mesh("tank", prof, lambda c: 1 if (c.z < band_z and X0 - 0.05 < c.x < X1 + 0.05) else 0)
tank.data.materials.append(TM["tank"]); tank.data.materials.append(TM["band"])
for x in (-4.0, -2.7, -1.4, -0.1, 1.2):                                     # bulkhead rings
    rg = ring_mesh("ring", [(x - 0.03, R + 0.004), (x - 0.015, R + 0.022), (x + 0.015, R + 0.022), (x + 0.03, R + 0.004)], lambda c: 0, seg=72)
    rg.data.materials.append(TM["steel"])
for z in (-1, 1): tbox(7.6, 0.035, 0.012, TM["stripe"], (-1.4, 2.03, z * 1.062), bevel=0.0)  # pinstripes

# top: walkway trough, overturn guards, front box, manholes
tbox(7.2, 0.08, 0.72, TM["steel"], (-1.4, 3.36, 0), bevel=0.006)
for z in (-0.39, 0.39):
    tbox(7.2, 0.18, 0.025, TM["tank"], (-1.4, 3.47, z), bevel=0.006)
    for x in [-4.9 + 0.9 * i for i in range(9)]: tbox(0.03, 0.16, 0.06, TM["tank"], (x, 3.47, z), bevel=0.004)
tbox(0.3, 0.32, 1.0, TM["tank"], (2.2, 3.5, 0), bevel=0.03)
for x in (1.6, 0.4, -0.8, -2.0, -3.2, -4.4):
    tcyl(0.23, 0.05, TM["steel"], (x, 3.44, 0), seg=32)                      # collar
    d = tcyl(0.2, 0.06, TM["tank"], (x, 3.49, 0), seg=32)                    # domed lid
    bv = d.modifiers.new("bevel", "BEVEL"); bv.width = 0.025; bv.segments = 4
    tcyl(0.05, 0.03, TM["steel"], (x, 3.535, 0), seg=16)                     # vent cap
    tbox(0.1, 0.05, 0.07, TM["steel"], (x, 3.5, -0.22))                      # hinge
    for a in (0.6, 2.2, 3.8, 5.4): tbox(0.03, 0.05, 0.03, TM["chrome"], (x + 0.21 * math.cos(a), 3.49, 0.21 * math.sin(a)), bevel=0.004)

# saddles, chassis rails, cross members
for x in (-4.6, -2.0, 0.6, 2.0): tbox(0.28, 0.42, 1.6, TM["chassis"], (x, 1.22, 0), bevel=0.02)
for z in (-0.45, 0.45):
    tbox(10.4, 0.28, 0.06, TM["chassis"], (-0.45, 0.85, z), bevel=0.006)
    for s in (-1, 1): tbox(10.4, 0.03, 0.09, TM["chassis"], (-0.45, 0.85 + s * 0.125, z - 0.03 * (1 if z > 0 else -1)), bevel=0.0)
for x in (-5.0, -3.0, -1.0, 1.0, 3.0): tbox(0.08, 0.2, 0.9, TM["chassis"], (x, 0.85, 0), bevel=0.0)

# side fittings: underrun guards, marker lamps, fuel tanks, hose tubes, tool box, grounding socket box
for z in (-1, 1):
    for y in (0.55, 0.85): tcyl(0.03, 2.6, TM["steel"], (-0.9, y, z * 1.12), axis="x", seg=12)
    for x in (-2.2, 0.4): tbox(0.05, 0.42, 0.04, TM["chassis"], (x, 0.7, z * 1.1), bevel=0.0)
    for x in (-5.0, -3.6, -2.2, -0.8, 0.6, 1.9): tbox(0.12, 0.06, 0.035, TM["amber"], (x, 1.72, z * 1.07), bevel=0.01)
    ft = tcyl(0.28, 0.9, TM["steel"], (2.5, 0.62, z * 0.86), axis="x", seg=32)
    for dx in (-0.36, 0.36): tcyl(0.29, 0.03, TM["chassis"], (2.5 + dx, 0.62, z * 0.86), axis="x", seg=32)
for y in (0.98, 1.17): tcyl(0.075, 3.0, TM["steel"], (-0.3, y, 1.02), axis="x", seg=16)
tbox(0.7, 0.42, 0.42, TM["steel"], (1.75, 0.92, 0.95), bevel=0.02)
if not EXPORT:
    tbox(0.5, 0.32, 0.14, TM["steel"], (-1.4, 1.05, -1.2), bevel=0.015)
    tcyl(0.045, 0.06, TM["green"], (-1.4, 1.05, -1.29), axis="z", seg=16)

# ---------- wheels: tyres with rounded shoulders, alloy rims, hubs and nuts; curved fenders ----------
def wheel(x, z):
    t = tcyl(0.5, 0.3, TM["tire"], (x, 0.52, z), axis="z", seg=48)
    bv = t.modifiers.new("bevel", "BEVEL"); bv.width = 0.09; bv.segments = 5; bv.limit_method = "ANGLE"
    for k in range(40):                                                           # tread blocks
        a = 2 * math.pi * k / 40
        tb = tbox(0.07, 0.025, 0.22, TM["tire"], (x + 0.505 * math.cos(a), 0.52 + 0.505 * math.sin(a), z), rz=a + math.pi / 2, bevel=0.0)
    s = 1 if z > 0 else -1
    tcyl(0.32, 0.31, TM["rim"], (x, 0.52, z), axis="z", seg=40)
    tcyl(0.27, 0.02, TM["chassis"], (x, 0.52, z + s * 0.15), axis="z", seg=40)
    tcyl(0.13, 0.06, TM["rim"], (x, 0.52, z + s * 0.17), axis="z", seg=24)
    for k in range(10):
        a = 2 * math.pi * k / 10
        tcyl(0.018, 0.03, TM["chrome"], (x + 0.09 * math.cos(a), 0.52 + 0.09 * math.sin(a), z + s * 0.2), axis="z", seg=6)
    tcyl(0.05, 0.05, TM["chrome"], (x, 0.52, z + s * 0.2), axis="z", seg=16)
WHEEL_PARTS = []
if EXPORT:
    before = set(TCOL.objects); wheel(0.0, 1.0); WHEEL_PARTS = [o for o in TCOL.objects if o not in before]
else:
    for x in (-4.7, -3.55, -2.4, 3.9):
        for z in (-1.0, 1.0): wheel(x, z)
for z in (-1.02, 1.02):                     # flat tandem fender over the three rear axles, ends turned down
    tbox(3.3, 0.03, 0.44, TM["chassis"], (-3.55, 1.16, z), bevel=0.008)
    for s in (-1, 1): tbox(0.32, 0.03, 0.44, TM["chassis"], (-3.55 + s * 1.76, 1.06, z), rz=s * 0.65, bevel=0.008)
    tbox(3.3, 0.06, 0.02, TM["chassis"], (-3.55, 1.13, z * 1.21), bevel=0.004)

# ---------- rear: bumper, hazard board, tail lamps, mud flaps, ladder ----------
tbox(0.2, 0.32, 2.36, TM["chassis"], (-5.78, 0.75, 0), bevel=0.03)
tbox(0.02, 0.24, 2.2, TM["hazard"], (-5.89, 0.72, 0), bevel=0.0)
for k in range(9):                                                              # red chevrons on the hazard board
    tbox(0.022, 0.24, 0.1, TM["red"], (-5.892, 0.72, -1.0 + k * 0.25), bevel=0.0).rotation_euler.x = 0.6
for z in (-0.85, 0.85):
    tbox(0.07, 0.18, 0.36, TM["red"], (-5.9, 0.98, z), bevel=0.02)
    tbox(0.07, 0.08, 0.12, TM["amber"], (-5.9, 0.98, z * 1.25), bevel=0.01)
for z in (-1, 1): tbox(0.025, 0.5, 0.5, TM["plastic"], (-5.3, 0.45, z), bevel=0.005)
LADDER_X = -5.62   # clear of the rear head (its surface reaches x -5.48 at the ladder's offset)
for z in (-0.62, -0.28): tcyl(0.022, 2.95, TM["steel"], (LADDER_X, 2.3, z), seg=12)
y = 1.0
while y < 3.7:
    tcyl(0.016, 0.34, TM["steel"], (LADDER_X, y, -0.45), axis="z", seg=10); y += 0.3
for yy in (1.9, 3.1):                                                          # standoff brackets to the tank head
    for z in (-0.62, -0.28): tbox(0.2, 0.03, 0.03, TM["steel"], (LADDER_X + 0.09, yy, z), bevel=0.0)

# ---------- cab-over cab (Korean heavy-truck style: high roof, raked screen, black grille, lamps in the bumper) ----------
def block(w, h, d, mat, pos, rake=0.0, taper=0.0, bevel=0.12, seg=5):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*pos))
    o = bpy.context.object; o.scale = (w, d, h); bpy.ops.object.transform_apply(scale=True)
    for v in o.data.vertices:
        if v.co.z > 0:
            v.co.y *= (1 - taper)
            if v.co.x > 0: v.co.x -= rake
    finish(o, mat, col=TCOL); bv = o.modifiers.new("bevel", "BEVEL"); bv.width = bevel; bv.segments = seg
    for p in o.data.polygons: p.use_smooth = True
    return o
CAB_Y0, CAB_H, RAKE = 0.925, 2.25, 0.28
block(2.1, CAB_H, 2.44, TM["cab"], (3.9, CAB_Y0 + CAB_H / 2, 0), rake=RAKE, taper=0.04, bevel=0.16, seg=6)
block(1.95, 0.42, 2.3, TM["cab"], (3.82, 3.38, 0), rake=0.35, taper=0.06, bevel=0.14)          # high roof
def front_x(y): return 4.95 - RAKE * (y - CAB_Y0) / CAB_H
tilt = math.atan2(RAKE, CAB_H)
tbox(0.02, 1.07, 2.27, TM["plastic"], (front_x(2.52) + 0.002, 2.52, 0), rz=tilt, bevel=0.04)   # screen surround
tbox(0.02, 0.95, 2.13, TM["glass"], (front_x(2.52) + 0.014, 2.52, 0), rz=tilt, bevel=0.05)     # windscreen
for z in (0.45, -0.5): tcyl(0.012, 0.85, TM["plastic"], (front_x(2.1) + 0.03, 2.1, z), axis="z", seg=6)  # wipers lying along the screen foot
tbox(0.03, 0.66, 1.62, TM["plastic"], (front_x(1.52) + 0.01, 1.52, 0), rz=tilt, bevel=0.05)    # grille
for y in (1.3, 1.45, 1.6, 1.75): tbox(0.02, 0.035, 1.46, TM["chrome"], (front_x(y) + 0.03, y, 0), rz=tilt, bevel=0.006)
tbox(2.12, 0.22, 2.47, TM["plastic"], (3.9, 1.02, 0), bevel=0.05)                               # dark lower trim
tbox(0.3, 0.42, 2.44, TM["plastic"], (4.95, 0.78, 0), bevel=0.07)                               # bumper
for z in (-1, 1):
    tbox(0.1, 0.2, 0.5, TM["plastic"], (5.0, 1.12, z * 0.83), bevel=0.03)                       # headlamp housing
    tbox(0.04, 0.14, 0.42, TM["head"], (5.05, 1.12, z * 0.83), bevel=0.02)
    tbox(0.04, 0.08, 0.12, TM["amber"], (5.05, 1.12, z * 1.13), bevel=0.01)
    tcyl(0.055, 0.04, TM["head"], (5.1, 0.72, z * 0.78), axis="x", seg=16)                     # fog lamp
    tbox(1.05, 0.8, 0.02, TM["plastic"], (4.2, 2.55, z * 1.214), bevel=0.04)                    # side window frame
    tbox(0.98, 0.72, 0.02, TM["glass"], (4.21, 2.56, z * 1.222), bevel=0.04)
    tbox(0.012, 1.9, 0.006, TM["plastic"], (3.52, 2.1, z * 1.222), bevel=0.0)                  # door seam
    tbox(0.18, 0.035, 0.03, TM["chrome"], (3.66, 2.02, z * 1.232), bevel=0.01)                  # handle
    for yy in (0.6, 0.92): tbox(0.32, 0.04, 0.26, TM["steel"], (4.62, yy, z * 1.12), bevel=0.01)  # steps ahead of the wheel
    for k in range(7):                                                                           # front wheel arch
        a = math.radians(25 + 130 * k / 6)
        tbox(0.27, 0.03, 0.36, TM["plastic"], (3.9 + 0.62 * math.cos(a), 0.52 + 0.62 * math.sin(a), z * 1.08), rz=a + math.pi / 2, bevel=0.0)
    tbox(0.5, 1.5, 0.02, TM["cab"], (2.62, 2.35, z * 1.2), bevel=0.03)                          # cab-side air deflector
    tcyl(0.015, 0.32, TM["plastic"], (4.8, 2.75, z * 1.36), axis="z", seg=8)                    # mirror arm
    tbox(0.1, 0.5, 0.24, TM["plastic"], (4.76, 2.45, z * 1.56), bevel=0.03)                     # mirror housing
    tbox(0.02, 0.44, 0.2, TM["glass"], (4.7, 2.45, z * 1.56), bevel=0.01)
tbox(0.32, 0.06, 2.3, TM["plastic"], (front_x(3.12) + 0.12, 3.17, 0), bevel=0.02)               # sun visor
for z in (-0.6, -0.3, 0.0, 0.3, 0.6): tbox(0.05, 0.04, 0.1, TM["amber"], (4.42, 3.56, z), bevel=0.01)  # roof marker lamps
# 위험물 board on the roof (black, yellow letters), as on Korean tank lorries
tbox(0.05, 0.3, 1.1, TM["plastic"], (4.3, 3.78, 0), bevel=0.01)
for z in (-0.45, 0.45): tbox(0.04, 0.2, 0.04, TM["plastic"], (4.3, 3.6, z), bevel=0.0)
FONT_KR = r"C:\Windows\Fonts\malgunbd.ttf"
if os.path.exists(FONT_KR):
    bpy.ops.object.text_add(location=B(4.33, 3.78, 0))
    t = bpy.context.object; t.data.body = "위험물"; t.data.font = bpy.data.fonts.load(FONT_KR)
    t.data.size = 0.2; t.data.align_x = "CENTER"; t.data.align_y = "CENTER"; t.data.extrude = 0.004
    t.rotation_euler = (math.pi / 2, 0, -math.pi / 2)   # facing forward after the mirror below
    bpy.ops.object.convert(target="MESH")
    finish(t, TM["stripe"], col=TCOL)

# mirror into place: cab to the west, rear ladder east by the LC
if not EXPORT:
    root = bpy.data.objects.new("tanker_root", None); bpy.context.scene.collection.objects.link(root)
    root.location = B(0.6, 0, 0); root.scale = (-1, 1, 1)
    for o in list(TCOL.objects): o.parent = root

# ---------- shots ----------
if "--shots" in args:
    out = args[args.index("--shots") + 1]; os.makedirs(out, exist_ok=True)
    r = scn.render; r.resolution_x, r.resolution_y = 1280, 720
    r.engine = "CYCLES"; scn.cycles.samples = 96; scn.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences; prefs.compute_device_type = "CUDA"; prefs.get_devices()
        for dv in prefs.devices: dv.use = True
        scn.cycles.device = "GPU"
    except Exception as e: print("GPU unavailable:", e)
    scn.view_settings.view_transform = "AgX"
    shot("tank_all", (11.5, 7.2, -11.0), (1.0, 2.3, -0.6), out)
    shot("tank_rear", (11.0, 2.6, -6.0), (3.5, 1.9, 0.0), out, fov=40)
    shot("tank_cab", (-10.0, 2.2, -6.0), (-3.0, 1.8, 0.0), out, fov=40)

# ---------- reference images on white: hero 3/4 plus orthographic front, left, rear, top ----------
if "--refs" in args:
    out = args[args.index("--refs") + 1]; os.makedirs(out, exist_ok=True)
    COL.hide_render = True; CTX.hide_render = True
    r = scn.render; r.film_transparent = True
    r.engine = "CYCLES"; scn.cycles.samples = 128; scn.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences; prefs.compute_device_type = "CUDA"; prefs.get_devices()
        for dv in prefs.devices: dv.use = True
        scn.cycles.device = "GPU"
    except Exception as e: print("GPU unavailable:", e)
    scn.view_settings.view_transform = "AgX"; scn.view_settings.exposure = 0.45
    scn.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.1
    def ref(name, pos, target, res, ortho=None, fov=30):
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name)); scn.collection.objects.link(cam)
        cam.location = B(*pos); cam.data.clip_end = 400
        if ortho: cam.data.type = "ORTHO"; cam.data.ortho_scale = ortho
        else: cam.data.sensor_fit = "VERTICAL"; cam.data.angle_y = math.radians(fov)
        d = B(*target) - B(*pos)
        cam.rotation_euler = d.to_track_quat("-Z", "Y" if abs(d.normalized().z) < 0.99 else "X").to_euler()
        scn.camera = cam; r.resolution_x, r.resolution_y = res; r.filepath = os.path.join(out, name + ".png")
        bpy.ops.render.render(write_still=True)
    ref("ref_hero", (-12.0, 4.0, 9.5), (0.7, 1.7, 0.0), (1600, 1000), fov=28)
    ref("ref_front", (-20.0, 1.95, 0.0), (0.0, 1.95, 0.0), (1024, 1024), ortho=4.4)
    ref("ref_rear", (25.0, 1.95, 0.0), (0.0, 1.95, 0.0), (1024, 1024), ortho=4.4)
    ref("ref_left", (1.0, 1.9, 20.0), (1.0, 1.9, 0.0), (1600, 640), ortho=12.6)
    ref("ref_top", (1.0, 25.0, 0.0), (1.0, 0.0, 0.0), (1600, 640), ortho=12.6)

# ---------- web export: tanker_body (truck-local frame) + tanker_wheel (centred, hub facing +z) ----------
if EXPORT:
    path = args[args.index("--export") + 1]
    def merge(objs, name):
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs: o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        bpy.ops.object.convert(target="MESH")            # applies bevels and other modifiers
        bpy.ops.object.join(); o = bpy.context.object; o.name = name; o.data.name = name
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)   # vertices in the truck frame, node at the origin
        return o
    wheel_o = merge(WHEEL_PARTS, "tanker_wheel")
    body_o = merge([o for o in TCOL.objects if o is not wheel_o], "tanker_body")
    c = B(0.0, 0.52, 1.0)                                # wheel centre to the origin
    wheel_o.data.transform(__import__("mathutils").Matrix.Translation(-c))
    bpy.ops.object.select_all(action="DESELECT"); body_o.select_set(True); wheel_o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
                              export_cameras=False, export_lights=False, export_animations=False,
                              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
                              export_draco_position_quantization=14, export_draco_normal_quantization=10)
    print("EXPORTED", path, len(body_o.data.polygons), len(wheel_o.data.polygons))
