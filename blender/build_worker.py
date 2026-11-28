"""Build the MPFB operator in metres. Use -- --shots DIRECTORY and/or --export FILE.glb."""
import argparse
import importlib
import math
import os
import sys
from pathlib import Path

import addon_utils
import bpy
import bmesh
import numpy as np

from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import build_driver as driver  # Initializes a clean Blender scene and the studio materials.
from build_driver import gear

MPFB = "bl_ext.blender_org.mpfb"
library = Path(bpy.utils.extension_path_user(MPFB)) / "data"
# MPFB opens hundreds of logs and builds a fitting cache during registration.
# Direct its runtime files to the ignored build directory for this process.
mpfb = importlib.import_module(MPFB)
get_preference = mpfb.get_preference
runtime = HERE / "out" / "mpfb_runtime"
runtime.mkdir(parents=True, exist_ok=True)
mpfb.get_preference = lambda key: str(runtime) if key == "mpfb_user_data" else get_preference(key)
mpfb.__time__ = os.path.getmtime(mpfb.__file__)
addon_utils.enable(MPFB, default_set=True)
from bl_ext.blender_org.mpfb.services.assetservice import AssetService
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.targetservice import TargetService

PREFIX = "mixamorig:"
scn = bpy.context.scene


def asset(category, filename):
    installed = list((library / category).rglob(filename))
    if installed:
        return str(installed[0])
    path = AssetService.find_asset_absolute_path(filename, category)
    if not path:
        raise FileNotFoundError(f"MPFB system asset missing: {category}/{filename}")
    return path


def human():
    macro = TargetService.get_default_macro_info_dict()
    macro.update(gender=1., age=.61, muscle=.54, weight=.54,
                 race={"asian": 1., "african": 0., "caucasian": 0.})
    body = HumanService.create_human(macro_detail_dict=macro, scale=.108)
    rig = HumanService.add_builtin_rig(body, "mixamo")
    def fit(category, name):
        return HumanService.add_mhclo_asset(
            asset(category, name + ".mhclo"), body, asset_type=category,
            subdiv_levels=0, material_type="NONE", import_subrig=False)
    suit = fit("clothes", "male_casualsuit01")
    eyes = fit("eyes", "high-poly")
    brows = fit("eyebrows", "eyebrow004")
    lashes = fit("eyelashes", "eyelashes01")
    hair = fit("hair", "short04")
    return rig, body, suit, eyes, brows, lashes, hair


def activate(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def rest_mesh(obj):
    """Bake MPFB morph targets and garment masks while keeping skin weights and UVs."""
    graph = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(graph), preserve_all_data_layers=True, depsgraph=graph)
    obj.modifiers.clear()
    obj.data = mesh


def bind(obj, rig, rigid=None):
    if rigid:
        obj.vertex_groups.new(name=PREFIX + rigid).add(range(len(obj.data.vertices)), 1, "REPLACE")
    obj.parent = rig
    mod = obj.modifiers.new("Mixamo skin", "ARMATURE")
    mod.object = rig
    return obj


def painted(obj, name, category, filename, roughness, alpha=False, tint=None):
    img = bpy.data.images.load(asset(category, filename), check_existing=True)
    if max(img.size) > 1024:
        img.scale(*(round(v * 1024 / max(img.size)) for v in img.size))
    mat = gear.pm(name, 0xffffff, roughness)
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    color = tex.outputs["Color"]
    if tint:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1
        mix.inputs[6].default_value = (*tint, 1)
        nt.links.new(color, mix.inputs[7])
        color = mix.outputs[2]
    nt.links.new(color, bsdf.inputs["Base Color"])
    if alpha:
        nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def detail_skin(body):
    # Preserve the source texels around the eyes, lips and cheeks. The hands
    # are gloved, so the rest of the full-body UV atlas can be much smaller.
    base=body.data.materials[0]
    tile=next(n for n in base.node_tree.nodes if n.type=="TEX_IMAGE").image
    tile.reload()
    w,h=tile.size
    pixels=np.empty(w*h*4,dtype=np.float32)
    tile.pixels.foreach_get(pixels)
    crop=pixels.reshape(h,w,4)[h//4:3*h//4,w//2:w].copy()
    face=bpy.data.images.new("middleage_asian_male_face",width=crop.shape[1],height=crop.shape[0])
    face.colorspace_settings.name=tile.colorspace_settings.name
    face.pixels.foreach_set(crop.ravel())
    face.pack()
    tile.scale(512,512)
    mat=base.copy()
    mat.name="Middleage Asian male - face detail"
    next(n for n in mat.node_tree.nodes if n.type=="TEX_IMAGE").image=face
    slot=len(body.data.materials)
    body.data.materials.append(mat)
    uv=body.data.uv_layers.active.data
    for f in body.data.polygons:
        if f.material_index or f.center.z<1.49:
            continue
        coords=[uv[i].uv.copy() for i in f.loop_indices]
        if all(.501<u<.999 and .251<v<.749 for u,v in coords):
            f.material_index=slot
            for i,(u,v) in zip(f.loop_indices,coords):
                uv[i].uv=(2*u-1,2*v-.5)


def dye_trousers(suit):
    # The trousers occupy the two central UV islands of casualsuit01. Retain
    # pocket stitching and folds, toning down the washed denim highlights.
    image=next(n for n in suit.data.materials[0].node_tree.nodes if n.type=="TEX_IMAGE").image
    w,h=image.size
    pixels=np.empty(w*h*4,dtype=np.float32)
    image.pixels.foreach_get(pixels)
    cloth=pixels.reshape(h,w,4)[:,int(.355*w):int(.715*w),:3]
    value=cloth @ np.array([.22,.69,.09],dtype=np.float32)
    sample=value[int(h*.79):int(h*.86),int(.15*w):int(.20*w)]
    level=max(.01,float(np.median(sample)))
    dye=np.clip(value/level,0,2)**.72
    cloth[:]=dye[:,:,None]*np.array((.205,.286,.39),dtype=np.float32)
    image.pixels.foreach_set(pixels)
    image.update()

def simplify(obj, ratio):
    activate(obj)
    m = obj.modifiers.new("Mobile topology", "DECIMATE")
    m.ratio = ratio
    bpy.ops.object.modifier_apply(modifier=m.name)


def dress(rig, body, suit, eyes, brows, lashes, hair):
    # Keep the collar opening. MPFB's garment mask cuts straight across the
    # chest here, which leaves a hole visible from above the unbuttoned shirt.
    for mod in body.modifiers:
        if mod.name.startswith("Delete."):
            group = body.vertex_groups.get(mod.vertex_group)
            if group:
                group.remove([v.index for v in body.data.vertices if abs(v.co.x)<.11 and v.co.z>1.29])
    objects = [body, suit, eyes, brows, lashes, hair]
    for obj, label in zip(objects, ["body", "uniform", "eyes", "brows", "lashes", "hair"]):
        obj.name = "worker_" + label
        rest_mesh(obj)
        obj.data.polygons.foreach_set("use_smooth", [True] * len(obj.data.polygons))
    painted(body, "Middleage Asian male", "skins", "middleage_lightskinned_male_diffuse2.png", .57)
    painted(suit, "Blue cotton workwear", "clothes", "male_casualsuit01_diffuse.png", .88,
            tint=(.68,.83,.95))

    # The open shirt collar sits inside the vest at the base of the neck.
    for v in suit.data.vertices:
        x,y,z=v.co
        if y<0 and abs(x)<.125 and z>1.405:
            tuck=np.interp(z,(1.405,1.48),(0,1))*np.interp(abs(x),(.055,.095,.125),(0,1,0))
            v.co.x*=1-.15*tuck
            v.co.y+=.014*tuck
    painted(eyes, "Brown iris", "eyes", "brown_eye.png", .24, True)
    # The iris sits behind a separate corneal shell in the high-poly eye.
    # Keep the studio reflection off the recessed, pigment-bearing surface.
    iris=eyes.data.materials[0].node_tree.nodes.get("Principled BSDF")
    iris.inputs["Specular IOR Level"].default_value=.065
    iris.inputs["Roughness"].default_value=.56
    painted(brows, "Brows", "eyebrows", "eyebrow004.png", .83, True)
    painted(lashes, "Lashes", "eyelashes", "eyelashes01.png", .85, True)
    painted(hair, "Cropped dark hair", "hair", "short04_diffuse.png", .83, True, (.18,.15,.14))
    # Remove the fully enclosed legs and trunk as well as the installed clothes' masks.
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < (1.29 if abs(v.co.x)<.11 else 1.42) and abs(v.co.x)<.395], context="VERTS")
    bmesh.ops.bisect_plane(bm,geom=[*bm.verts,*bm.edges,*bm.faces], dist=.00001,
                           plane_co=(0,0,1.458),plane_no=(0,-.25,1))
    bm.to_mesh(body.data)
    bm.free()
    body.data.materials.append(driver.M["glove"])
    body.data.materials.append(gear.pm("Crew neck undershirt", 0x243040, .91))
    for f in body.data.polygons:
        if abs(f.center.x) > .395:
            f.material_index = 1
        elif f.center.z < 1.458 + .25*f.center.y:
            f.material_index = 2
    for v in body.data.vertices:
        if abs(v.co.x) > .395:
            v.co += v.normal * .0018
    # Trim the crown inside the hard hat while retaining sideburns and nape.
    bm = bmesh.new()
    bm.from_mesh(hair.data)
    bmesh.ops.bisect_plane(bm,geom=[*bm.verts,*bm.edges,*bm.faces],dist=.00001,
                           plane_co=(0,0,1.694),plane_no=(0,0,1),clear_outer=True)
    bm.to_mesh(hair.data)
    bm.free()
    for obj, ratio in [(body,.80),(suit,.67),(eyes,.60)]:
        simplify(obj,ratio)
    detail_skin(body)
    dye_trousers(suit)
    for obj in objects:
        bind(obj,rig)
    return objects


def surface(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
    return BVHTree.FromPolygons([v.co for v in mesh.vertices], triangles, all_triangles=True), triangles


def skin_from_suit(obj, rig, suit, tree, triangles):
    for v in obj.data.vertices:
        p, _, index, _ = tree.find_nearest(v.co)
        tri = [suit.data.vertices[i] for i in triangles[index]]
        uv = barycentric_transform(p, *(u.co for u in tri), Vector((1,0,0)), Vector((0,1,0)), Vector((0,0,1)))
        weights = {}
        for u, w in zip(tri, uv):
            for g in u.groups:
                name = suit.vertex_groups[g.group].name
                if name.startswith(PREFIX):
                    if obj.name.startswith("gear_legloop"):
                        side = "Left" if obj.name.endswith("L") else "Right"
                        if ("Leg" in name and side not in name) or "Arm" in name:
                            continue
                    elif any(part in name for part in ("Arm","Hand","Leg","Thumb","Index","Middle","Ring","Pinky")):
                        continue
                    weights[name] = weights.get(name, 0) + max(0,w) * g.weight
        top = sorted(weights.items(), key=lambda item:-item[1])[:4]
        if not top:
            top = [(PREFIX+("Spine2" if v.co.z>1.25 else "Hips"),1)]
        total = sum(w for _,w in top)
        for name,w in top:
            if w>0:
                group = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
                group.add([v.index], w/total, "REPLACE")
    bind(obj,rig)


def fit_equipment(rig, suit, old_parts):
    tree, triangles = surface(suit)
    equipment = []
    for name in ("gear_vest","gear_harness","gear_legloop_L","gear_legloop_R"):
        src = old_parts[name]
        src.name = "comparison_" + name
        obj = bpy.data.objects.new(name, src.data.copy())
        scn.collection.objects.link(obj)
        obj.data.transform(src.matrix_world)
        loop = "legloop" in name
        side = 1 if name.endswith("L") else -1
        if loop:
            pts = [v.co for v in suit.data.vertices]
            faces = [t for t in triangles if all(side*pts[i].x>-.002 and pts[i].z<1.02 for i in t)]
            thigh = BVHTree.FromPolygons(pts,faces,all_triangles=True)
        for v in obj.data.vertices:
            x,y,z = v.co
            # Map each layer's signed clearance from the original torso or thigh
            # onto a section through the MPFB garment at the corresponding height.
            if loop and z < .83:
                center = Vector((side*.122,-.012,z-.033))
                offset = Vector((x-side*.1,y,0))
                ref = .087
            elif loop and z < .975:
                hit = tree.ray_cast(Vector((x,.35,z)), Vector((0,-1,0)))[0]
                if hit:
                    v.co.y = hit.y + .006 + max(0,y-.116)
                continue
            else:
                # A single continuous warp preserves the approved spacing between
                # shell, tape, webbing and buckles, even across armholes.
                levels = (.98,1.04,1.10,1.22,1.30,1.36,1.42,1.49)
                wx = np.interp(z,levels,(1.05,1.16,1.10,.99,1.00,1.02,1.04,1.07))
                dy = np.interp(z,levels,(1.24,1.30,1.28,1.18,1.20,1.25,1.27,1.27))
                lift = np.interp(z,(1.29,1.42,1.49),(0,.019,.034))
                v.co = (x*wx,y*dy-.009+np.interp(z,(1.22,1.39),(0,.019)),z+lift)
                if not loop:
                    inward = Vector((x, y, 0)).normalized()
                    v.co -= inward * .004 * np.interp(z,(1.09,1.24),(1,0))
                # Tailor the armhole inside the deltoid silhouette. Keep the
                # shoulder tapes and the front and back panels on the same cut.
                armhole=np.interp(abs(x),(.095,.165),(0,1))*np.interp(z,(1.245,1.39),(0,1))
                v.co.z -= armhole*.046
                v.co.x *= 1-.085*armhole
                v.co.y += np.sign(y)*armhole*.018
                crown=np.interp(z,(1.405,1.485),(0,1))
                v.co.z -= .009*crown
                if y>0:
                    v.co.y += .020 * np.interp(z,(.99,1.10,1.33,1.43),(0,1,1,0))
                if z>1.40:
                    v.co.z -= .009*np.interp(z,(1.40,1.47),(0,1))
                continue
            direction = offset.normalized()
            hit = thigh.ray_cast(center+direction*.23, -direction, .28)[0]
            if hit:
                clearance = offset.length-ref
                radius = (hit-center).length + max(0,clearance) + .006
                v.co = center + direction*radius
        if name=="gear_vest":
            # Reseat both reflective bands on the finished, triangulated shell.
            pts=[v.co for v in obj.data.vertices]
            base=[tuple(f.vertices) for f in obj.data.polygons if obj.data.materials[f.material_index]==gear.M["vest"]]
            tape_support=BVHTree.FromPolygons(pts,base)
            for f in obj.data.polygons:
                mat=obj.data.materials[f.material_index]
                if mat not in (gear.M["tape"],gear.M["tape_edge"]):
                    continue
                for i in f.vertices:
                    v=obj.data.vertices[i]
                    if v.co.z>1.30:
                        continue
                    d=Vector((v.co.x,v.co.y,0)).normalized()
                    hit=tape_support.ray_cast(v.co+d*.09,-d,.20)[0]
                    if hit:
                        dist=.003 if mat==gear.M["tape"] else .004
                        v.co=hit+d*dist
        obj.data.update()
        skin_from_suit(obj,rig,suit,tree,triangles)
        equipment.append(obj)
    return equipment


def seat_shoulders(rig, suit, equipment, old_parts):
    """Map the approved yoke onto the relaxed shirt, keeping each layer's clearance."""
    pose_worker(rig,"front")
    graph=bpy.context.evaluated_depsgraph_get()
    fabric,_=surface(suit.evaluated_get(graph))
    points,faces=[],[]
    for key in ("drv_torso","drv_uparm_L","drv_uparm_R"):
        obj=old_parts[key]
        start=len(points)
        points.extend(obj.matrix_world@v.co for v in obj.data.vertices)
        faces.extend(tuple(start+i for i in f.vertices) for f in obj.data.polygons)
    template=BVHTree.FromPolygons(points,faces)
    # Sample a common, smooth displacement field instead of shrinkwrapping
    # the inner and outer edges of every strap independently.
    widths=np.linspace(-.202,.202,31)
    angles=np.linspace(0,math.pi,39)
    offsets=np.zeros((len(widths),len(angles)))
    for i,x in enumerate(widths):
        for j,angle in enumerate(angles):
            axis=Vector((0,-math.cos(angle),math.sin(angle)))
            sx=math.copysign(max(abs(x),.087*math.sin(angle)**2),x)
            c=Vector((sx,0,1.30))
            a=template.ray_cast(c+axis*.36,-axis,.34)[0]
            b=fabric.ray_cast(c+axis*.36,-axis,.34)[0]
            if a and b:
                offsets[i,j]=np.clip((b-a).dot(axis),-.035,.065)
    for _ in range(3):
        pad=np.pad(offsets,1,mode="edge")
        offsets=(4*offsets+pad[1:-1,:-2]+pad[1:-1,2:]+pad[:-2,1:-1]+pad[2:,1:-1])/8
    transforms={b.name:b.matrix @ b.bone.matrix_local.inverted() for b in rig.pose.bones}
    for obj in equipment[:2]:
        original=old_parts[obj.name]
        posed=[v.co.copy() for v in obj.evaluated_get(graph).data.vertices]
        for v in obj.data.vertices:
            q=original.matrix_world@original.data.vertices[v.index].co
            if q.z<1.255:
                continue
            angle=math.atan2(max(0,q.z-1.30),-q.y)
            delta=np.interp(q.x,widths,[np.interp(angle,angles,row) for row in offsets])
            axis=Vector((0,-math.cos(angle),math.sin(angle)))
            clearance = .009 if obj.name=="gear_harness" else .002
            target=q+axis*(delta+clearance)
            amount=np.interp(q.z,(1.255,1.34),(0,1))
            # Invert linear-blend skinning once to store this fit in rest space.
            matrix=Matrix(((0,0,0),(0,0,0),(0,0,0)))
            for g in v.groups:
                name=obj.vertex_groups[g.group].name
                if name in transforms:
                    matrix+=transforms[name].to_3x3()*g.weight
            v.co+=matrix.inverted_safe()@((target-posed[v.index])*amount)
        obj.data.update()
    for b in rig.pose.bones:
        b.matrix_basis=Matrix.Identity(4)
    bpy.context.view_layer.update()

def finish_trim(vest,harness):
    points=[v.co.copy() for v in vest.data.vertices]
    base=[tuple(f.vertices) for f in vest.data.polygons if vest.data.materials[f.material_index]==gear.M["vest"]]
    support=BVHTree.FromPolygons(points,base)
    idx={i for f in vest.data.polygons if vest.data.materials[f.material_index]==gear.M["tape"]
         for i in f.vertices if points[i].z>1.31}
    for i in idx:
        p=points[i]
        radial=Vector((0,p.y,max(0,p.z-1.32))).normalized()
        hit=support.ray_cast(p+radial*.045,-radial,.085)[0]
        if hit:
            vest.data.vertices[i].co=hit+radial*.0035
    # The dorsal ring stands proud of its mounting plate.
    ring={i for f in harness.data.polygons if harness.data.materials[f.material_index]==gear.M["metal"]
          for i in f.vertices if harness.data.vertices[i].co.z>1.30 and harness.data.vertices[i].co.y>0}
    for i in ring:
        harness.data.vertices[i].co.y+=.012
    vest.data.update()
    harness.data.update()

def headgear(body, rig):
    col = driver.collection("Helmet components")
    # Translate the procedural shell into the fitted head's local frame.
    delta = Vector((0,-.044,.033))
    class Scalp:
        def ray_cast(self,start,axis):
            hit,p,n,i = body.ray_cast(start+delta,axis)
            return hit,p-delta,n,i
    driver.helmet(col,Scalp())
    for obj in list(col.objects):
        if obj.data.materials[0] in (driver.M["web_dark"],driver.M["plastic"]):
            bpy.data.objects.remove(obj,do_unlink=True)
        else:
            for v in obj.data.vertices:
                v.co.x *= 1.035
                v.co.y *= 1.035
                v.co += delta

    # Fit the chin strap in front of the ears and across the underside of the jaw.
    for sign in (1,-1):
        route = [(.096,-.076,1.685),(.085,-.082,1.654),(.080,-.087,1.618),
             (.071,-.092,1.578),(.060,-.100,1.548),(.045,-.108,1.522),
             (.028,-.114,1.506),(.014,-.116,1.501),(0,-.116,1.499)]
        rows=[]
        stations=[Vector(a).lerp(Vector(b),t/4) for a,b in zip(route,route[1:]) for t in range(4)]
        for x,y,z in [*stations,route[-1]]:
            radial=Vector((sign*min(1,x/.036),0,-max(0,1-x/.046))).normalized()
            row=[]
            for width in (-.004,.004):
                q=Vector((x*sign,y+width,z))
                hit,loc,_,_=body.ray_cast(q+radial*.06,-radial,distance=.105)
                if hit and z<1.664:
                    q=loc+radial*.002
                row.append((q.x,q.z,-q.y))
            rows.append(row)
        driver.patch(col,"web_dark",rows)
    pieces = list(col.objects)
    activate(pieces[0])
    for obj in pieces:
        obj.select_set(True)
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = "worker_head_gear"

    bind(obj,rig,"Head")
    return obj


def aim(rig, name, direction):
    bone = rig.pose.bones[PREFIX+name]
    basis = bone.matrix.to_quaternion()
    adjust = (bone.tail-bone.head).rotation_difference(Vector(direction))
    bone.rotation_quaternion = bone.rotation_quaternion @ (basis.inverted() @ adjust @ basis)
    bpy.context.view_layer.update()


def pose_worker(rig, kind):
    for bone in rig.pose.bones:
        bone.rotation_mode = "QUATERNION"
        bone.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    for side,s in (("Left",1),("Right",-1)):
        aim(rig,side+"Arm",(s*.29,.045,-1))
        aim(rig,side+"ForeArm",(s*.03,-.19,-1))
    if kind=="pose":
        aim(rig,"RightUpLeg",(-.075,-.643,-.766))
        aim(rig,"RightLeg",(-.05,.5,-.866))
        aim(rig,"LeftArm",(.16,-1,0))
        aim(rig,"LeftForeArm",(-.10,-.70,.70))
    if kind=="face":
        aim(rig,"LeftArm",(.55,-.52,-.60))
        aim(rig,"LeftForeArm",(-.48,.13,.87))
        aim(rig,"LeftHand",(-.44,.14,.89))
        hand = rig.pose.bones[PREFIX+"LeftHand"]
        hand.rotation_quaternion @= Quaternion((0,1,0),math.radians(-55))
    head = rig.pose.bones[PREFIX+"Head"]
    q = head.matrix.to_quaternion()
    turn = {"pose":-20,"face":-7}.get(kind,0)
    head.rotation_quaternion = q.inverted() @ Quaternion((0,0,1), math.radians(turn)) @ q
    bpy.context.view_layer.update()


def build_worker():
    for mat in (*driver.M.values(), *gear.M.values()):
        mat.use_fake_user = True
    rig, body, suit, *features = human()
    rig.name = "worker_rig"
    pieces = dress(rig, body, suit, *features)
    old, parts = driver.build_driver()
    equipment = fit_equipment(rig,suit,parts)
    seat_shoulders(rig,suit,equipment,parts)
    finish_trim(*equipment[:2])
    pieces += equipment
    for s, suffix, side in ((1,"L","Left"),(-1,"R","Right")):
        src = parts["drv_boot_"+suffix]
        boot = bpy.data.objects.new("worker_boot_"+suffix,src.data.copy())
        scn.collection.objects.link(boot)
        boot.data.transform(src.matrix_world)
        ankle = rig.data.bones[PREFIX+side+"Foot"].head_local
        boot.data.transform(Matrix.Translation((ankle.x-s*.1,ankle.y,0)))
        for v in boot.data.vertices:
            t=np.interp(v.co.z,(.065,.12,.18),(0,.55,1))
            v.co.x=ankle.x+(v.co.x-ankle.x)*(1-.40*t)-s*.010*t
            v.co.y=ankle.y+(v.co.y-ankle.y)*(1-.35*t)
        bind(boot,rig,side+"Foot")
        pieces.append(boot)
    pieces.append(headgear(body,rig))
    count = 0
    for obj in pieces:
        obj.data.calc_loop_triangles()
        bone_groups={g.index for g in obj.vertex_groups if g.name in rig.data.bones}
        unweighted=sum(not any(w.group in bone_groups and w.weight>0 for w in v.groups) for v in obj.data.vertices)
        if unweighted:
            raise ValueError(f"{obj.name}: {unweighted} vertices without Mixamo weights")
        n = len(obj.data.loop_triangles)
        print("WORKER",obj.name,n,flush=True)
        count += n
    print("TOTAL",count,flush=True)
    if count>40000:
        raise ValueError("Worker exceeds mobile triangle budget")
    for n in ("Hips","LeftUpLeg","LeftLeg","LeftFoot","LeftArm","LeftForeArm","Head"):
        print("JOINT",n,rig.data.bones[PREFIX+n].head_local.z)
    for img in bpy.data.images:
        if img.users:
            print("TEXTURE",img.name,tuple(img.size))
    return rig, old, pieces


def bake_standing_rest(rig, pieces):
    rig.location = (0, 0, 0)
    pose_worker(rig, "front")
    for obj in pieces:
        # dress() already resolved the MPFB shape keys before binding.
        activate(obj)
        bpy.ops.object.modifier_apply(modifier=obj.modifiers["Mixamo skin"].name)
    activate(rig)
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    for obj in pieces:
        bind(obj, rig)
    bpy.context.view_layer.update()


def export_worker(path, rig, pieces):
    materials = {m for obj in pieces for m in obj.data.materials if m}
    for mat in materials:
        shader = mat.node_tree.nodes.get("Principled BSDF")
        # The procedural grain varies around the socket's original dye colour.
        for key, source in (("Base Color", "VALTORGB"), ("Normal", "BUMP")):
            for link in list(shader.inputs[key].links):
                if link.from_node.type == source:
                    mat.node_tree.links.remove(link)
        for key in ("Metallic", "Emission Strength", "Anisotropic IOR Level",
                    "Subsurface Weight", "Sheen Weight"):
            if key in shader.inputs:
                shader.inputs[key].default_value = 0
        shader.inputs["Specular IOR Level"].default_value = .5
        shader.inputs["IOR"].default_value = 1.5
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE":
                img = node.image
                limit = 512 if mat.name in ("Brown iris", "Cropped dark hair") else 1024
                if max(img.size) > limit:
                    img.scale(*(round(n * limit / max(img.size)) for n in img.size))
                if img.is_dirty:
                    img.pack()
    activate(rig)
    for obj in pieces:
        obj.select_set(True)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", use_selection=True,
        export_skins=True, export_animations=False, export_cameras=False,
        export_lights=False, export_yup=True, export_image_format="JPEG",
        export_image_quality=82, export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=7, export_draco_position_quantization=14,
        export_draco_normal_quantization=10, export_draco_texcoord_quantization=12,
        export_draco_generic_quantization=0)
    print("EXPORTED", path, path.stat().st_size, flush=True)


def render(out, rig, old, only=None, draft=False):
    out.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault("OPTIX_CACHE_PATH",str(HERE/"out"/"cycles_cache"))
    cam = driver.studio()
    for name, direction, target, height, size in [
        ("compare",(.52,.16,1),(0,.89,0),1.99,(1000,880)),
        ("front",(0,.07,1),(0,.89,0),1.98,(640,900)),
        ("back",(0,.07,-1),(0,.89,0),1.98,(640,900)),
        ("side",(1,.07,0),(0,.89,0),1.98,(640,900)),
        ("pose",(-1.14,.14,1),(0,.89,.04),2.04,(760,900)),
        ("face",(.30,.06,1),(.081,1.578,.085),.48,(880,800))]:
        if only and name not in only:
            continue
        compare = name=="compare"
        old.users_collection[0].hide_render = not compare
        offset = gear.B(1,0,-.52).normalized()*.42
        old.location = -offset
        rig.location = offset if compare else (0,0,0)
        pose_worker(rig,name)
        scn.cycles.samples = 4 if draft else (36 if name=="face" else 20)
        cam.location = gear.B(*target)+gear.B(*direction).normalized()*5
        cam.rotation_euler = (-gear.B(*direction)).to_track_quat("-Z","Y").to_euler()
        cam.data.ortho_scale = height*max(1,size[0]/size[1])
        scn.render.resolution_x,scn.render.resolution_y = size
        scn.render.resolution_percentage = 55 if draft else 100
        scn.render.filepath = str(out/("worker_"+name+".png"))
        bpy.ops.render.render(write_still=True)


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shots", type=Path)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--only",nargs="+")
    parser.add_argument("--draft",action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    if not (args.shots or args.export):
        parser.error("supply --shots and/or --export")
    rig, old, pieces = build_worker()
    if args.shots:
        render(args.shots.resolve(), rig, old, args.only, args.draft)
    if args.export:
        bake_standing_rest(rig, pieces)
        export_worker(args.export.resolve(), rig, pieces)















