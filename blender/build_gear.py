# Hi-vis vest and full-body harness for the driver, in the driver rig's own frame (metres, +z = the driver's front).
# Torso parts follow `rig`, leg loops follow each hip joint at (+-0.1, 0.92, 0) in preview/index.html.
# Run: blender -b -P blender/build_gear.py -- --shots out_dir   (current look vs new gear, front and back)
import bpy, bmesh, math, os, sys
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

def B(x, y, z): return Vector((x, -z, y))
def srgb(h):
    c = [((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255]
    return [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c] + [1]

if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene

def pm(name, color, rough=0.7, metal=0.0, emit=None, img=None):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb(color); b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    if emit: b.inputs["Emission Color"].default_value = srgb(emit[0]); b.inputs["Emission Strength"].default_value = emit[1]
    if img:
        nt = m.node_tree; it = nt.nodes.new("ShaderNodeTexImage"); it.image = img
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.inputs["Factor"].default_value = 1
        mix.inputs[6].default_value = srgb(color); nt.links.new(it.outputs["Color"], mix.inputs[7]); nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    return m

def mesh_tile(n=64):
    """knitted safety-mesh look: small holes on a square grid, tiled over the vest."""
    img = bpy.data.images.new("vest_mesh", n, n); px = []
    for y in range(n):
        for x in range(n):
            dx, dy = (x % 8) - 3.5, (y % 8) - 3.5
            v = 0.88 if dx * dx + dy * dy < 5.5 else 1.0
            px += [v, v, v, 1.0]
    img.pixels = px; img.pack(); return img

M = {
    "jacket": pm("jacket", 0x2c3444, 0.85), "jeans": pm("jeans", 0x3a5478, 0.9), "boot": pm("boot", 0x2a2420, 0.65),
    "skin": pm("skin", 0xe8b894, 0.6), "helmet": pm("helmet", 0xf2f2ee, 0.4), "glove": pm("glove", 0x3c4a40, 0.85),
    "hair": pm("hair", 0x231d19, 0.95),
    # the page's current gear
    "vest_old": pm("vest_old", 0xf28c28, 0.75), "refl_old": pm("refl_old", 0xe4e8e6, 0.3, emit=(0x888888, 0.35)), "harn_old": pm("harness_old", 0xb7322a, 0.75),
    # new gear
    "vest": pm("vest_hivis", 0xff7a1a, 0.8, img=mesh_tile()), "vest_edge": pm("vest_binding", 0xc85a10, 0.7),
    "tape": pm("retro_tape", 0xd9dee0, 0.32, 0.25, emit=(0x9aa0a2, 0.25)), "tape_edge": pm("tape_edge", 0xf2c230, 0.6),
    "zip": pm("zip", 0x1f2222, 0.5), "web": pm("webbing", 0xc0262a, 0.7), "web_dark": pm("webbing_black", 0x1d1f1f, 0.75),
    "metal": pm("harness_metal", 0xb8bfc2, 0.25, 1.0), "plastic": pm("harness_plastic", 0x202323, 0.5), "badge": pm("badge", 0xf4f4ee, 0.4),
}

def add_obj(name, me, col):
    o = bpy.data.objects.new(name, me); col.objects.link(o); return o

def lathe(pts, mat, y0, sx, sz, col, seg=40, x0=0.0, z0=0.0, smooth=True, close_top=False):
    me = bpy.data.meshes.new("lathe"); bm = bmesh.new(); rings = []
    for r, h in pts:
        rings.append([bm.verts.new(B(x0 + r * sx * math.sin(2 * math.pi * i / seg), y0 + h, z0 + r * sz * math.cos(2 * math.pi * i / seg))) for i in range(seg)])
    for j in range(len(rings) - 1):
        for i in range(seg):
            f = bm.faces.new((rings[j][i], rings[j][(i + 1) % seg], rings[j + 1][(i + 1) % seg], rings[j + 1][i])); f.smooth = smooth
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    o = add_obj("lathe", me, col); o.data.materials.append(mat); return o

def prim(kind, mat, pos, col, scale=(1, 1, 1), rot=(0, 0, 0), **kw):
    getattr(bpy.ops.mesh, "primitive_" + kind + "_add")(location=B(*pos), **kw)
    o = bpy.context.object
    for c in o.users_collection: c.objects.unlink(o)
    col.objects.link(o); o.scale = scale; o.rotation_euler = rot; o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth = True
    return o

# ---------- body (identical for both figures; matches the page's hand-built driver) ----------
VEST = [(0.153, 0.06), (0.158, 0.1), (0.173, 0.2), (0.188, 0.3), (0.184, 0.38), (0.162, 0.43), (0.13, 0.455)]
TORSO = [(0.001, 0), (0.15, 0.0), (0.155, 0.08), (0.17, 0.2), (0.185, 0.3), (0.18, 0.38), (0.15, 0.44), (0.07, 0.48), (0.001, 0.49)]
SX, SZ, Y0 = 1.13, 0.755, 0.98

def body(x0, col):
    lathe(TORSO, M["jacket"], Y0, 1.12, 0.74, col, x0=x0)
    lathe([(0.001, 0), (0.13, 0.0), (0.152, 0.16), (0.001, 0.16)], M["jeans"], 0.85, 1.12, 0.74, col, x0=x0)
    prim("uv_sphere", M["jacket"], (x0, 1.365, 0), col, scale=(0.23, 0.05, 0.06), radius=1, segments=24, ring_count=12)  # shoulder yoke
    for sx_ in (-0.1, 0.1):
        x = x0 + sx_
        prim("cone", M["jeans"], (x, 0.70, 0), col, radius1=0.064, radius2=0.084, depth=0.44, vertices=20)
        prim("cone", M["jeans"], (x, 0.28, 0), col, radius1=0.05, radius2=0.062, depth=0.40, vertices=20)
        prim("cube", M["boot"], (x, 0.045, 0.03), col, scale=(0.11, 0.22, 0.09), size=1.0)
    for sx_ in (-0.232, 0.232):
        x = x0 + sx_
        prim("uv_sphere", M["jacket"], (x, 1.38, 0), col, radius=0.05, segments=16, ring_count=10)
        prim("cone", M["jacket"], (x, 1.24, 0), col, radius1=0.046, radius2=0.051, depth=0.3, vertices=16)
        prim("cone", M["jacket"], (x, 0.965, 0), col, radius1=0.036, radius2=0.045, depth=0.25, vertices=16)
        prim("uv_sphere", M["glove"], (x, 0.8, 0.005), col, scale=(0.85, 0.6, 1.25), radius=0.045, segments=16, ring_count=10)
    prim("cylinder", M["skin"], (x0, 1.48, 0), col, radius=0.048, depth=0.1, vertices=14)
    prim("uv_sphere", M["skin"], (x0, 1.6, 0), col, scale=(0.93, 1, 1.1), radius=0.105, segments=24, ring_count=16)
    prim("uv_sphere", M["helmet"], (x0, 1.66, 0), col, scale=(1, 1.08, 0.86), radius=0.122, segments=28, ring_count=14)
    prim("cylinder", M["helmet"], (x0, 1.65, 0.03), col, scale=(0.9, 1.12, 1), radius=0.136, depth=0.01, vertices=32)

# ---------- the page's current gear ----------
def old_gear(x0, col):
    lathe(VEST, M["vest_old"], Y0, SX, SZ, col, x0=x0)
    for y in (1.12, 1.29): lathe([(0.183, 0), (0.175, 0.03)], M["refl_old"], y - 0.015, 1.13, 0.765, col, x0=x0)
    for x in (-0.085, 0.085):
        for z in (0.141, -0.141): prim("cube", M["refl_old"], (x0 + x, 1.34, z), col, scale=(0.028, 0.004, 0.14), size=1.0)
    for x in (-0.07, 0.07):
        for z in (0.142, -0.142): prim("cube", M["harn_old"], (x0 + x, 1.22, z), col, scale=(0.045, 0.005, 0.46), size=1.0)
    lathe([(0.168, 0), (0.165, 0.045)], M["harn_old"], 0.9675, 1.08, 0.82, col, x0=x0)
    for x in (-0.1, 0.1): lathe([(0.088, 0), (0.085, 0.04)], M["harn_old"], 0.78, 1, 1, col, x0=x0 + x)
    prim("torus", M["metal"], (x0, 1.38, -0.155), col, rot=(0, 0, 0), major_radius=0.04, minor_radius=0.01, major_segments=20, minor_segments=8)

# ---------- new gear: straps are flat ribbons laid on the body surface ----------
def interp(prof, y):
    pts = [(h + Y0, r) for r, h in prof]
    if y <= pts[0][0]: return pts[0][1]
    for (y1, r1), (y2, r2) in zip(pts, pts[1:]):
        if y1 <= y <= y2: return r1 + (r2 - r1) * (y - y1) / (y2 - y1)
    return pts[-1][1]
def body_r(y): return interp(VEST, y) if y >= 1.04 else 0.168 * (1.08 / SX) if y < 1.02 else interp(VEST, 1.04)
def surf(x, y, front=True, off=0.0, x0=0.0):
    """point on the vest surface at lateral x and height y, pushed out by off."""
    r = body_r(y); s = max(-0.999, min(0.999, x / (r * SX))); a = math.asin(s)
    if not front: a = math.pi - a
    p = Vector((r * SX * math.sin(a), y, r * SZ * math.cos(a)))
    n = Vector((math.sin(a) / SX, 0, math.cos(a) / SZ)).normalized()
    return (p + n * off + Vector((x0, 0, 0)), n)
def ring_pts(y, off, x0=0.0, rscale=1.0, n=40):
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n; r = body_r(y) * rscale
        p = Vector((x0 + r * SX * math.sin(a), y, r * SZ * math.cos(a))); nn = Vector((math.sin(a) / SX, 0, math.cos(a) / SZ)).normalized()
        out.append((p + nn * off, nn))
    return out

def catmull(pts, k=6, closed=False):
    P = [p for p, _ in pts]; N = [n for _, n in pts]; out = []; m = len(P)
    rng = range(m) if closed else range(m - 1)
    for i in rng:
        p0, p1, p2, p3 = P[(i - 1) % m if closed else max(i - 1, 0)], P[i], P[(i + 1) % m], P[(i + 2) % m if closed else min(i + 2, m - 1)]
        n1, n2 = N[i], N[(i + 1) % m]
        for j in range(k):
            t = j / k; t2, t3 = t * t, t * t * t
            p = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            out.append((p, (n1.lerp(n2, t)).normalized()))
    if not closed: out.append((P[-1], N[-1]))
    return out

def strap(pts, w, th, mat, col, closed=False, k=6, name="strap"):
    pts = catmull(pts, k, closed); m = len(pts)
    me = bpy.data.meshes.new(name); bm = bmesh.new(); quads = []
    for i, (p, n) in enumerate(pts):
        t = (pts[(i + 1) % m][0] - pts[(i - 1) % m][0]) if closed else (pts[min(i + 1, m - 1)][0] - pts[max(i - 1, 0)][0])
        side = t.cross(n).normalized(); n2 = side.cross(t).normalized()
        a, b = p - side * w / 2, p + side * w / 2
        quads.append([bm.verts.new(B(*v)) for v in (a, b, b + n2 * th, a + n2 * th)])
    rng = range(m) if closed else range(m - 1)
    for i in rng:
        q1, q2 = quads[i], quads[(i + 1) % m]
        for e in range(4): bm.faces.new((q1[e], q1[(e + 1) % 4], q2[(e + 1) % 4], q2[e]))
    if not closed:
        bm.faces.new(quads[0][::-1]); bm.faces.new(quads[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    o = add_obj(name, me, col); o.data.materials.append(mat); return o

def up_n(n, u): return (n * (1 - u) + Vector((0, 1, 0)) * u).normalized()

def new_gear(x0, col, *, harness_col=None, leg_cols=None, ring_steps=6):
    # vest shell: same cut as the page's vest, thicker, with a V-neck at the front
    v = lathe(VEST, M["vest"], Y0, SX * 1.01, SZ * 1.01, col, seg=48, x0=x0)
    bm = bmesh.new(); bm.from_mesh(v.data)
    kill = [f for f in bm.faces if (c := f.calc_center_median()).y < 0 and c.z > 1.26 and abs(c.x - x0) < 0.02 + (c.z - 1.26) * 0.9]
    bmesh.ops.delete(bm, geom=kill, context="FACES"); bm.to_mesh(v.data); bm.free()
    sol = v.modifiers.new("thick", "SOLIDIFY"); sol.thickness = 0.005; sol.offset = 1
    # UVs for the mesh-fabric tile
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = v; v.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT"); bpy.ops.uv.cylinder_project(scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT"); v.select_set(False)
    for f in v.data.uv_layers.active.data: f.uv = (f.uv[0] * 60, f.uv[1] * 20)
    # shoulder panels joining front and back over each shoulder
    for s in (-1, 1):
        x = s * 0.12
        pts = [surf(x, 1.36, True, 0.004, x0), surf(x * 1.02, 1.42, True, 0.004, x0),
               (Vector((x0 + x * 1.05, 1.475, 0.0)), Vector((0, 1, 0))),
               surf(x * 1.02, 1.42, False, 0.004, x0), surf(x, 1.36, False, 0.004, x0)]
        pts[1] = (pts[1][0], up_n(pts[1][1], 0.5)); pts[3] = (pts[3][0], up_n(pts[3][1], 0.5))
        strap(pts, 0.095, 0.005, M["vest"], col, name="vest_shoulder")
        strap(pts, 0.045, 0.0065, M["tape"], col, name="tape_shoulder")                           # tape over the shoulder
    # two retro-reflective bands with thin yellow edges, and the hem binding
    for y in (1.105, 1.225):
        strap(ring_pts(y, 0.0062, x0, 1.01), 0.05, 0.002, M["tape"], col, closed=True, k=ring_steps, name="tape_band")
        for dy in (-0.027, 0.027): strap(ring_pts(y + dy, 0.0063, x0, 1.01), 0.004, 0.002, M["tape_edge"], col, closed=True, k=ring_steps, name="tape_edge")
    strap(ring_pts(1.045, 0.0055, x0, 1.01), 0.014, 0.003, M["vest_edge"], col, closed=True, k=ring_steps, name="hem")
    # front zip, pocket with flap, ID badge holder
    strap([surf(0, 1.05, True, 0.0068, x0), surf(0, 1.15, True, 0.0068, x0), surf(0, 1.26, True, 0.0068, x0)], 0.012, 0.002, M["zip"], col, name="zip")
    p, n = surf(0, 1.255, True, 0.009, x0); prim("cube", M["metal"], (p.x, p.y - 0.012, p.z + 0.004), col, scale=(0.012, 0.006, 0.028), size=1.0)
    p, n = surf(-0.09, 1.075, True, 0.008, x0)
    pk = prim("cube", M["vest"], (p.x, p.y, p.z), col, scale=(0.075, 0.012, 0.085), size=1.0); pk.rotation_euler = (0, 0, math.atan2(n.x, n.z))
    fl = prim("cube", M["vest_edge"], (p.x, p.y + 0.042, p.z + 0.004), col, scale=(0.078, 0.014, 0.02), size=1.0); fl.rotation_euler = pk.rotation_euler
    p, n = surf(0.095, 1.29, True, 0.008, x0)
    bd = prim("cube", M["badge"], (p.x, p.y, p.z), col, scale=(0.055, 0.006, 0.075), size=1.0); bd.rotation_euler = (0, 0, math.atan2(n.x, n.z))

    # ---- full-body harness: red webbing, black hardware ----
    col = harness_col if harness_col is not None else col
    W, T, OFF = 0.044, 0.005, 0.012
    belt = ring_pts(0.99, 0.0, x0, 1.0)
    belt = [(Vector((x0 + (pp.x - x0) * 1.0, pp.y, pp.z)) + nn * 0.0, nn) for pp, nn in
            [(Vector((x0 + 0.181 * math.sin(2 * math.pi * i / 40), 0.99, 0.138 * math.cos(2 * math.pi * i / 40))), Vector((math.sin(2 * math.pi * i / 40) / 1.08, 0, math.cos(2 * math.pi * i / 40) / 0.82)).normalized()) for i in range(40)]]
    strap(belt, 0.05, 0.006, M["web"], col, closed=True, k=ring_steps, name="belt")
    pad = [(Vector((x0 + 0.188 * math.sin(a), 0.99, 0.145 * math.cos(a))), Vector((math.sin(a), 0, math.cos(a))).normalized()) for a in [math.pi * (0.62 + 0.76 * i / 10) for i in range(11)]]
    strap(pad, 0.085, 0.01, M["web_dark"], col, name="back_pad")
    for s in (-1, 1):                                                                             # side D-rings
        prim("torus", M["metal"], (x0 + s * 0.195, 0.99, 0.0), col, rot=(0, math.pi / 2, 0), major_radius=0.026, minor_radius=0.005, major_segments=20, minor_segments=8)
    prim("cube", M["metal"], (x0, 0.99, 0.15), col, scale=(0.05, 0.012, 0.05), size=1.0)           # belt buckle
    # shoulder straps: belt front -> chest -> over the shoulder -> cross at the back D-ring -> down to the sub-pelvic strap
    for s in (-1, 1):
        x = s * 0.075
        pts = [surf(x, 1.0, True, OFF, x0), surf(x * 1.05, 1.16, True, OFF, x0), surf(x * 1.2, 1.30, True, OFF, x0),
               surf(x * 1.45, 1.40, True, OFF, x0),
               (Vector((x0 + x * 1.5, 1.49, 0.0)), Vector((0, 1, 0))),
               surf(x * 1.3, 1.40, False, OFF, x0), surf(s * 0.02, 1.33, False, OFF + 0.004, x0),
               surf(-s * 0.06, 1.18, False, OFF, x0), surf(-s * 0.085, 1.0, False, OFF, x0)]
        pts[3] = (pts[3][0], up_n(pts[3][1], 0.4)); pts[5] = (pts[5][0], up_n(pts[5][1], 0.4))
        strap(pts, W, T, M["web"], col, name="shoulder_strap")
        p, n = surf(x * 1.05, 1.16, True, OFF + 0.006, x0)                                            # adjuster buckles
        b_ = prim("cube", M["metal"], (p.x, p.y, p.z), col, scale=(0.05, 0.008, 0.02), size=1.0); b_.rotation_euler = (0, 0, math.atan2(n.x, n.z))
    # chest strap with a two-part buckle
    strap([surf(-0.13, 1.255, True, OFF + 0.006, x0), surf(-0.04, 1.27, True, OFF + 0.012, x0), surf(0.04, 1.27, True, OFF + 0.012, x0), surf(0.13, 1.255, True, OFF + 0.006, x0)], 0.032, T, M["web"], col, name="chest_strap")
    p, n = surf(0, 1.27, True, OFF + 0.02, x0); prim("cube", M["plastic"], (p.x, p.y, p.z), col, scale=(0.06, 0.01, 0.036), size=1.0)
    # dorsal D-ring on its plate
    p, n = surf(0, 1.335, False, OFF + 0.01, x0)
    prim("cube", M["web_dark"], (p.x, p.y, p.z), col, scale=(0.07, 0.008, 0.08), size=1.0)
    prim("torus", M["metal"], (p.x, p.y + 0.035, p.z - 0.012), col, rot=(math.radians(70), 0, 0), major_radius=0.034, minor_radius=0.0065, major_segments=24, minor_segments=8)
    # leg loops around each thigh (these follow the hip joints on the page) and the sub-pelvic strap joining them at the back
    for s in (-1, 1):
        if leg_cols is not None:
            col = leg_cols[s]
        cx = x0 + s * 0.1
        loop = [(Vector((cx + 0.087 * math.sin(a), 0.78 + 0.03 * math.cos(a) * s * 0.0, 0.087 * math.cos(a))), Vector((math.sin(a), 0, math.cos(a)))) for a in [2 * math.pi * i / 28 for i in range(28)]]
        strap(loop, W, T, M["web"], col, closed=True, k=ring_steps, name="leg_loop")
        prim("cube", M["metal"], (cx + s * 0.06, 0.78, 0.065), col, scale=(0.012, 0.05, 0.03), size=1.0)  # loop buckle
        sp = [surf(s * 0.085, 1.0, False, OFF, x0), (Vector((cx - s * 0.01, 0.88, -0.118)), Vector((0, 0, -1))), (Vector((cx, 0.8, -0.092)), Vector((0, 0, -1)))]
        strap(sp, W, T, M["web"], col, name="subpelvic")

# ---------- scene ----------
if __name__ == "__main__":
    OLD = bpy.data.collections.new("current"); NEW = bpy.data.collections.new("new")
    for c in (OLD, NEW): scn.collection.children.link(c)
    body(-0.45, OLD); old_gear(-0.45, OLD)
    body(0.45, NEW); new_gear(0.45, NEW)

    if "--shots" in args:
        out = os.path.abspath(args[args.index("--shots") + 1]); os.makedirs(out, exist_ok=True)
        w = bpy.data.worlds.new("w"); scn.world = w; w.use_nodes = True
        hdr = os.path.join(ROOT, "blender", "assets", "overcast_industrial_courtyard_2k.hdr")
        if os.path.exists(hdr):
            env = w.node_tree.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(hdr)
            w.node_tree.links.new(env.outputs["Color"], w.node_tree.nodes["Background"].inputs["Color"])
        sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scn.collection.objects.link(sun)
        sun.data.energy = 3.0; sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(30))
        bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0)); bpy.context.object.data.materials.append(pm("floor", 0x9a978f, 0.9))
        r = scn.render; r.resolution_x, r.resolution_y = 1600, 1000; r.engine = "CYCLES"; scn.cycles.samples = 96; scn.cycles.use_denoising = True
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences; prefs.compute_device_type = "CUDA"; prefs.get_devices()
            for dv in prefs.devices: dv.use = True
            scn.cycles.device = "GPU"
        except Exception as e: print("GPU unavailable:", e)
        scn.view_settings.view_transform = "AgX"; scn.view_settings.exposure = 0.3
        for name, pos in (("gear_front", (0.55, 1.45, 2.35)), ("gear_back", (-0.55, 1.45, -2.35))):
            cam = bpy.data.objects.new(name, bpy.data.cameras.new(name)); scn.collection.objects.link(cam)
            cam.location = B(*pos); cam.data.lens = 50
            cam.rotation_euler = (B(0, 1.1, 0) - B(*pos)).to_track_quat("-Z", "Y").to_euler()
            scn.camera = cam; r.filepath = os.path.join(out, name + ".png"); bpy.ops.render.render(write_still=True)
