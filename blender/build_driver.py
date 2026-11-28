# Articulated rack operator. All modelling coordinates are metres in the web rig frame.
# blender -b -P blender/build_driver.py -- --shots blender/out/driver_shots
# blender -b -P blender/build_driver.py -- --export preview/tex/driver_body.glb
import argparse
import math
import os
import sys
import time
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
bpy.ops.wm.read_factory_settings(use_empty=True)
import build_gear as gear

B, M = gear.B, gear.M.copy()
for key in ("jacket","glove","hair"):
    M[key]=M[key].copy()
sin, cos, pi = math.sin, math.cos, math.pi
scn = bpy.context.scene


def collection(name):
    col = bpy.data.collections.new(name)
    scn.collection.children.link(col)
    return col


def material(key, color, roughness, metal=0):
    M[key] = gear.pm(key, color, roughness, metal)


for spec in [
    ("twill", 0x394D65, .89), ("seam", 0x46596F, .88), ("cuff", 0x242D3A, .91),
    ("sleeve_panel", 0x303B4D, .84), ("leather", 0x382F29, .59), ("rubber", 0x252727, .82),
    ("welt", 0x50473C, .7), ("lace", 0x625E50, .91), ("eyelet", 0x746E5F, .38, .61),
    ("grip", 0x303A34, .91), ("knit", 0x4C5A4D, .94),
    ("complexion", 0xC98F70, .62), ("lips", 0xAC7160, .68), ("lip_line", 0x784D40, .8),
    ("brow", 0x503C31, .87), ("lash", 0x574039, .82), ("sclera", 0xBDADA0, .40),
    ("iris", 0x382B26, .41), ("pupil", 0x231E1C, .35), ("shell_edge", 0xD8DAD5, .47),
]:
    material(*spec)


def grain(key, scale, distance, strength):
    # Object coordinates keep the grain size constant across joined mesh islands.
    nt = M[key].node_tree
    uv = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 1.5
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = distance
    bump.inputs["Strength"].default_value = strength
    nt.links.new(uv.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
    if key not in ("complexion",):
        color=nt.nodes["Principled BSDF"].inputs["Base Color"]
        base=list(color.default_value)
        dye=nt.nodes.new("ShaderNodeValToRGB")
        for elem,factor,position in zip(dye.color_ramp.elements,(.69,1.25),(.24,.76)):
            elem.position=position
            elem.color=(*[v*factor for v in base[:3]],1)
        nt.links.new(noise.outputs["Fac"],dye.inputs["Fac"])
        nt.links.new(dye.outputs["Color"],color)


for k in ("jacket","twill", "sleeve_panel", "cuff", "glove", "knit", "leather", "complexion","brow"):
    grain(k, 1200 if k == "complexion" else 570, .00025, .22)


def mesh(col, name, verts, faces, mat, smooth=True):
    data = bpy.data.meshes.new(name)
    data.from_pydata([B(*p) for p in verts], [], faces)
    data.update()
    data.materials.append(M[mat])
    if smooth:
        data.polygons.foreach_set("use_smooth", [True] * len(data.polygons))
    return gear.add_obj(name, data, col)


def rings(col, name, rows, mat):
    # Ring order goes from the lower to the upper end, starting at the front.
    n = len(rows[0])
    faces = [(j*n+i, j*n+(i+1)%n, (j+1)*n+(i+1)%n, (j+1)*n+i)
             for j in range(len(rows)-1) for i in range(n)]
    last = (len(rows)-1)*n
    faces.extend([tuple(reversed(range(n))), tuple(range(last, last+n))])
    return mesh(col, name, [p for row in rows for p in row], faces, mat)


def power(v, exponent):
    return math.copysign(abs(v)**exponent, v)


def loft(col, name, mat, profile, x=0, n=20, exponent=1, cloth=False):
    # Sections specify height, half-width, half-depth, lateral shift, forward shift.
    rows = []
    for j, (h, w, d, dx, dz) in enumerate(profile):
        row = []
        for i in range(n):
            a = 2*pi*i/n
            rip = 1 + (.022*sin(3*a+8*h) + .014*sin(5*a-4*h) if cloth else 0)
            tilt = .006*sin(a+.7) + .004*cos(2*a+12*h) if cloth and 0 < j < len(profile)-1 else 0
            if cloth and 0 < j < len(profile)-1:
                for center,span,phase in ((.167,.036,.4),(.49,.058,1.2),(1.105,.052,2.7)):
                    weight=math.exp(-((h-center)/span)**2)
                    tilt+=weight*.009*sin(a+phase)
                    rip+=weight*.066*cos(72*(h-center)+1.8*cos(a+phase))*cos(a-.6)
            row.append((x+dx+w*power(sin(a), exponent)*rip, h+tilt,
                        dz+d*power(cos(a), exponent)*rip))
        rows.append(row)
    return rings(col, name, rows, mat)


def oval(col, mat, pos, radii, n=12, lat=8):
    x,y,z = pos
    w,h,d = radii
    profile = [(y+h*sin(t), max(.00012,w*cos(t)), max(.00012,d*cos(t)), 0,z)
               for t in [-pi/2+pi*i/lat for i in range(lat+1)]]
    return loft(col, mat, mat, profile, x, n)


def cord(col, mat, points, radii, n=7):
    # Parallel-transport the section along the path to avoid twisting the seam.
    pts = list(map(Vector, points))
    if isinstance(radii, (int, float)):
        radii = [radii]*len(pts)
    rows = []
    normal = None
    for i, (p, r) in enumerate(zip(pts, radii)):
        t = (pts[min(len(pts)-1, i+1)] - pts[max(0, i-1)]).normalized()
        if normal is None:
            normal = t.orthogonal().normalized()
        normal = (normal - t*normal.dot(t)).normalized()
        axis = t.cross(normal)
        rows.append([p + r*(normal*cos(2*pi*j/n) + axis*sin(2*pi*j/n)) for j in range(n)])
    return rings(col, mat, rows, mat)


def section(col, mat, s, x, profile, **kw):
    return loft(col, mat, mat, [(h,w,d,s*dx,dz) for h,w,d,dx,dz in profile], s*x, **kw)


def surface_stitch(col, obj, mat, points, direction, r):
    """Place a narrow welt on an actual fabric surface, including its folds."""
    direction=Vector(direction).normalized()
    seam=[]
    for p in points:
        hit,loc,normal,_=obj.ray_cast(B(*(Vector(p)+direction*.15)), -B(*direction))
        if hit:
            q=loc+normal*r*.30
            seam.append((q.x,q.z,-q.y))
    if len(seam)>1:
        cord(col,mat,seam,r,5)


def body_core(pelvis, torso, neck):
    seat=loft(pelvis, "seat", "twill", [
        (.843,.065,.054,0,-.008),(.86,.14,.089,0,-.010),(.895,.177,.121,0,-.009),
        (.945,.181,.127,0,-.008),(.977,.175,.121,0,0),(1.015,.16,.112,0,0)], n=32)
    surface_stitch(pelvis,seat,"seam",[(.012,.975,.12),(.012,.944,.12),(.012,.914,.12),
            (.010,.896,.12),(0,.886,.12)],(0,0,1),.0016)
    for s in (-1,1):
        surface_stitch(pelvis,seat,"seam",[(s*x,y,.1) for x,y in
            [(.09,.967),(.109,.952),(.13,.937),(.145,.927),(.159,.921)]],(0,0,1),.002)
    jacket=loft(torso, "jacket", "jacket", [
        (.978,.15,.111,0,0),(.99,.17,.124,0,.001),(1.012,.17,.126,0,0),
        (1.027,.165,.12,0,0),(1.038,.172,.118,0,0),(1.065,.17,.114,0,0),
        (1.14,.175,.118,0,0),(1.22,.191,.13,0,-.002),(1.30,.200,.136,0,-.002),
        (1.345,.209,.130,0,-.003),(1.374,.222,.120,0,-.003),(1.389,.225,.111,0,-.003),
        (1.404,.221,.105,0,-.003),(1.419,.210,.098,0,-.002),(1.433,.190,.089,0,-.002),
        (1.449,.155,.078,0,-.001),(1.462,.116,.065,0,0),(1.473,.069,.052,0,0)],n=36)
    # Taper the side of the yoke into the flatter sleeve cross section.
    for v in jacket.data.vertices:
        side=max(0,min(1,(abs(v.co.x)-.145)/.065))
        height=max(0,min(1,(v.co.z-1.26)/.075))
        v.co.y*=1-.24*side*height
    jacket.data.update()
    zipper=[(0,y,.14) for y in (1.25,1.30,1.355,1.39,1.422,1.435,1.451)]
    surface_stitch(torso,jacket,"cuff",zipper,(0,0,1),.0025)
    oval(torso,"eyelet",(0,1.437,.087),(.0027,.0064,.0018),8,4)
    for s in (-1,1):
        surface_stitch(torso,jacket,"sleeve_panel",[(s*x,y,.1) for x,y in
              [(.006,1.432),(.021,1.441),(.040,1.447),(.056,1.455),(.063,1.465)]],(0,0,1),.0014)
    loft(torso,"stand collar","cuff",[(1.431,.087,.075,0,0),(1.456,.084,.069,0,0),
             (1.477,.067,.061,0,0),(1.482,.065,.059,0,0)],n=28)
    loft(neck,"neck","complexion",[(1.455,.057,.052,0,0),(1.49,.054,.05,0,0),
             (1.52,.054,.052,0,.003),(1.554,.061,.056,0,.004)],n=24)


def leg(s, thigh, shin):
    section(thigh,"twill",s,.1,[
        (.447,.034,.035,0,.002),(.456,.055,.053,0,.002),(.476,.067,.067,0,.005),
        (.495,.069,.072,0,.004),(.515,.071,.067,.001,0),(.527,.069,.071,.001,-.002),
        (.549,.07,.068,.001,-.004),(.62,.075,.076,.002,-.002),(.70,.080,.081,.001,-.002),
        (.766,.082,.084,0,-.001),(.81,.085,.085,0,0),(.86,.092,.091,-.002,-.004),
        (.904,.098,.096,-.007,-.006),(.934,.09,.09,-.009,-.006),(.966,.068,.07,-.012,-.005),
        (.982,.032,.036,-.012,0)],cloth=True)
    section(shin,"twill",s,.1,[
        (.131,.061,.065,0,-.004),(.139,.067,.068,0,-.004),(.148,.068,.066,0,-.003),
        (.164,.061,.061,0,-.005),(.177,.066,.067,-.001,-.007),(.195,.06,.063,0,-.007),
        (.23,.059,.062,0,-.01),(.306,.066,.071,0,-.015),(.351,.072,.078,0,-.014),
        (.392,.073,.074,0,-.008),(.426,.068,.068,0,-.004),(.448,.065,.068,0,-.001),
        (.46,.069,.068,0,0),(.483,.066,.065,0,.003),(.504,.056,.05,0,.003),
        (.523,.029,.03,0,.002),(.527,.008,.01,0,.002)],cloth=True)
    # Side cargo pocket with a bellows edge and overlapping flap, aligned to the thigh.
    section(thigh,"twill",s,.1,[(.586,.008,.036,.067,-.005),(.592,.013,.051,.068,-.005),
             (.674,.013,.056,.073,-.002),(.686,.009,.05,.073,-.001)],n=16,exponent=.43)
    section(thigh,"seam",s,.1,[(.665,.009,.045,.078,0),(.675,.012,.054,.077,0),
             (.692,.009,.056,.075,0)],n=16,exponent=.48)
    cord(shin,"seam",[(s*(.1+w),y,z) for w,y,z in
         [(.064,.43,-.022),(.071,.38,-.029),(.067,.31,-.031),(.058,.23,-.024),
          (.060,.185,-.025),(.064,.146,-.024)]],.0013,5)


def boot(s, col):
    x = s*.1
    def upper(mat, prof, e=.71):
        return loft(col,mat,mat,[(h,w,d,0,z) for h,w,d,z in prof],x,24,e)
    # Tread blocks leave daylight under the arch between forefoot and heel.
    for z,span in [(-.052,.037),(-.026,.043),(.044,.047),(.074,.049),(.104,.049),(.134,.042),(.15,.027)]:
        for side in (-1,1):
            loft(col,"tread","rubber",[(.001,span*.47,.009,0,z),(.009,span*.52,.012,0,z)],
                 x+side*span*.57,6,.53)
    upper("rubber",[(.008,.052,.113,.045),(.014,.056,.122,.045),(.025,.058,.123,.045),
          (.029,.057,.121,.045)])
    upper("welt",[(.026,.058,.122,.045),(.031,.058,.122,.045),(.034,.056,.119,.045)])
    leather=upper("leather",[(.031,.055,.119,.045),(.05,.055,.117,.044),(.064,.054,.109,.041),
          (.073,.051,.094,.031),(.083,.048,.081,.018),(.104,.045,.064,.004),
          (.129,.047,.053,-.006),(.158,.046,.048,-.006),(.179,.044,.046,-.006)])
    # Cut the rubber cap and its welt into the last so they share vertices with
    # the leather, even after the boot is simplified.
    bm=bmesh.new()
    bm.from_mesh(leather.data)
    axis=B(0,-.5,1).normalized()
    center=B(x,.05,.085)
    for offset in (0,.0017):
        bmesh.ops.bisect_plane(bm,geom=[*bm.verts,*bm.edges,*bm.faces],dist=.00001,
                               plane_co=center+axis*offset,plane_no=axis)
    leather.data.materials.append(M["welt"])
    leather.data.materials.append(M["rubber"])
    for face in bm.faces:
        depth=(face.calc_center_median()-center).dot(axis)
        face.material_index=2 if depth>.0017 else int(depth>0)
    bm.to_mesh(leather.data)
    bm.free()
    for j in range(4):
        h=.081+j*.013
        front=.097-j*.013
        for side in (-1,1):
            xx=x+side*.028
            oval(col,"eyelet",(xx,h,front),(.0042,.0034,.0032),8,4)
            if j<3:
                cord(col,"lace",[(xx,h,front+.001),(x,h+.008,front+.002),
                     (x-side*.028,h+.013,front-.012)],.0022,6)
    upper("rubber",[(.151,.047,.049,-.006),(.158,.048,.049,-.006),
                     (.173,.047,.048,-.006),(.177,.045,.047,-.006)])


def arm(s, upper, fore):
    # Sections use absolute lateral centres. The deltoid sits medial to the
    # fixed shoulder pivot; the jacket yoke above it stays with the torso.
    sleeve=section(upper,"jacket",s,0,[
        (1.066,.017,.016,.218,-.007),(1.073,.032,.029,.218,-.008),
        (1.091,.0425,.037,.217,-.009),(1.106,.041,.035,.216,-.010),
        (1.119,.043,.038,.215,-.010),(1.141,.041,.036,.213,-.009),(1.195,.044,.039,.208,-.006),
        (1.252,.048,.043,.201,.002),(1.300,.051,.046,.192,.009),
        (1.344,.053,.048,.177,.009),(1.368,.051,.046,.178,.005),
        (1.385,.046,.041,.180,.002),(1.396,.034,.032,.181,0),
        (1.401,.013,.014,.181,0)])
    lower=section(fore,"jacket",s,0,[
        (.846,.029,.026,.221,.029),(.852,.032,.028,.221,.028),
        (.863,.033,.029,.222,.026),(.875,.030,.027,.223,.024),(.886,.032,.029,.224,.022),
        (.915,.033,.030,.227,.017),(.967,.037,.033,.231,.007),
        (1.007,.040,.035,.229,-.002),(1.044,.041,.037,.224,-.007),
        (1.073,.0395,.036,.219,-.009),(1.089,.040,.036,.217,-.009),
        (1.104,.035,.032,.217,-.007),(1.119,.018,.017,.218,-.003)])
    section(fore,"cuff",s,0,[(.822,.029,.027,.220,.032),(.825,.030,.028,.220,.031),
            (.847,.029,.026,.221,.029),(.854,.028,.025,.221,.028)])
    # Bias the gathered fabric towards the inside of the elbow and wrist.
    # Tipping just these rings keeps the deltoid and cuff edges smooth.
    for obj,center,span in [(sleeve,1.114,.027),(lower,.875,.022)]:
        for v in obj.data.vertices:
            weight=math.exp(-((v.co.z-center)/span)**2)
            v.co.z+=weight*(.15*(s*v.co.x-.222)+.09*v.co.y)
    surface_stitch(upper,sleeve,"sleeve_panel",[(s*.27,y,z) for y,z in [
        (1.382,-.020),(1.368,-.024),(1.344,-.026),(1.30,-.028),
        (1.252,-.029),(1.195,-.030),(1.141,-.029),(1.112,-.029)]],(s,0,0),.0012)
    glove(s,fore)


def glove(s,col):
    x=s*.220
    def pt(dx,y,z):
        return (x+s*dx,y,z+.022)
    section(col,"knit",s,.220,[(.807,.024,.033,0,.035),(.811,.026,.034,0,.035),
            (.822,.027,.026,0,.032),(.837,.026,.024,0,.031)])
    hand=section(col,"glove",s,.220,[(.737,.005,.017,.006,.041),(.746,.014,.034,.007,.036),(.757,.021,.043,.005,.035),
            (.773,.026,.045,.004,.037),(.794,.025,.044,.001,.036),
            (.811,.023,.033,0,.034),(.818,.023,.028,0,.034)],n=20,exponent=.85)
    # The palm faces the thigh. Fingers fan front-to-back and curl towards the palm.
    for j,(z,length,r) in enumerate([(.044,.053,.011),(.024,.061,.0115),(.003,.057,.0105),(-.016,.047,.0095)]):
        y=.758+(j==3)*.004
        pts=[pt(.009,y,z),pt(.009,y-.013,z+.001),pt(.003,y-length*.58,z+.002),
             pt(-.009,y-length*.88,z+.004),pt(-.019,y-length,z+.005),pt(-.024,y-length+.002,z+.005)]
        cord(col,"glove",pts,[r*.87,r,r*.94,r*.84,r*.70,.002],9)
        surface_stitch(col,hand,"knit",[pt(.027,y,z+offset) for y,offset in
             [(.795,-.002),(.785,-.001),(.776,0),(.768,0),(.759,.001)]],(s,0,0),.0008)
    cord(col,"glove",[pt(-.006,.795,.037),pt(-.011,.786,.051),pt(-.021,.77,.061),
         pt(-.029,.756,.063),pt(-.033,.75,.058),pt(-.034,.751,.054)],
         [.014,.016,.014,.012,.009,.003],10)


# Skull cross sections measured from chin to crown. Forward and rear depths are
# independent so that the occiput, mandibular angle and chin have distinct profiles.
SKULL = [
    (1.504,.018,.058,.012,.022),(1.510,.036,.076,.024,.014),
    (1.521,.052,.083,.038,.007),(1.537,.064,.084,.058,.004),
    (1.552,.071,.085,.071,.003),(1.575,.077,.087,.085,.001),
    (1.597,.081,.090,.094,0),(1.619,.082,.091,.098,-.001),
    (1.647,.083,.091,.099,-.002),(1.67,.082,.088,.097,-.002),
    (1.69,.074,.077,.087,-.002),(1.709,.045,.050,.064,-.003),
    (1.719,.012,.014,.015,-.003),
]


def sample(table, y):
    if y <= table[0][0]:
        return table[0][1:]
    for a,b in zip(table, table[1:]):
        if y <= b[0]:
            t=(y-a[0])/(b[0]-a[0])
            return tuple(v+(w-v)*t for v,w in zip(a[1:],b[1:]))
    return table[-1][1:]


def bell(x,y,cx,cy,w,h):
    return math.exp(-((x-cx)/w)**2-((y-cy)/h)**2)


def facial_relief(x,y):
    a=abs(x)
    return (.009*bell(a,y,.049,1.586,.027,.024)     # zygomatic arch
            -.008*bell(a,y,.034,1.611,.024,.014)    # eye socket
            +.006*bell(a,y,.032,1.627,.029,.011)    # brow ridge
            +.012*bell(x,y,0,1.544,.035,.017)       # muzzle
            +.009*bell(x,y,0,1.520,.022,.011)
            -.004*bell(a,y,.048,1.557,.016,.02)
            +.009*bell(x,y,0,1.607,.013,.026)      # bridge, tip and alae
            +.017*bell(x,y,0,1.584,.012,.026)
            +.018*bell(x,y,0,1.575,.014,.011)
            +.012*bell(a,y,.014,1.570,.008,.007)
            +.003*bell(a,y,.005,1.557,.003,.007))


def face_z(x,y):
    w,front,_,off=sample(SKULL,y)
    c=math.sqrt(max(0,1-(x/w)**2))
    return off+front*c**.82+facial_relief(x,y)*c


def patch(col,mat,rows):
    n=len(rows[0])
    faces=[(j*n+i,j*n+i+1,(j+1)*n+i+1,(j+1)*n+i)
           for j in range(len(rows)-1) for i in range(n-1)]
    return mesh(col,mat,[p for row in rows for p in row],faces,mat)


def eyes(col,s):
    # A narrow visible aperture over a convex cornea, sculpted lids flush with the socket.
    center=s*.032
    def outline(u):
        amp=max(0,1-u*u)**.78
        mid=1.610+s*.0014*u
        return mid-.0031*amp,mid+.0046*amp
    def cornea(x,y):
        u=(x-center)/.016
        low,high=outline(u)
        chord=((1-u)*face_z(center-.016,1.610-s*.0014)+(1+u)*face_z(center+.016,1.610+s*.0014))/2
        return chord+.0006+.0044*(1-u*u)-17*(y-(low+high)/2)**2
    us=[-1+i/7 for i in range(15)]
    for part in ("sclera","upper","lower"):
        rows=[]
        for k in range(4):
            t=k/3
            row=[]
            for u in us:
                x=center+.016*u
                low,high=outline(u)
                amp=max(0,1-u*u)**.6
                if part=="sclera":
                    y=low+t*(high-low)
                    z=cornea(x,y)
                else:
                    edge=high if part=="upper" else low
                    y=edge+(1 if part=="upper" else -1)*(.0004+.0065*amp)*t
                    z=(1-t)*cornea(x,edge)+t*(face_z(x,y)-.00025)+.0015*sin(pi*t)*amp
                row.append((x,y,z))
            rows.append(row)
        patch(col,"sclera" if part=="sclera" else "complexion",rows[::-1] if part=="lower" else rows)
    for mat,r,off in [("iris",.0055,.00018),("pupil",.0025,.00031)]:
        rows=[]
        for k in range(5):
            row=[]
            for j in range(13):
                u=-.999+1.998*j/12
                x=center+r*u
                low,high=outline((x-center)/.016)
                dy=r*math.sqrt(1-u*u)
                y0=max(low,1.6104-dy)
                y1=min(high,1.6104+dy)
                y=y0+(y1-y0)*k/4
                row.append((x,y,cornea(x,y)+off))
            rows.append(row)
        patch(col,mat,rows)
    glint_x=center-.0017
    glint_y=1.6123
    oval(col,"badge",(glint_x,glint_y,cornea(glint_x,glint_y)+.00048),
         (.00085,.00068,.00027),8,4)
    line=[]
    for u in us:
        x=center+.016*u
        y=outline(u)[1]
        line.append((x,y,cornea(x,y)+.00022))
    cord(col,"lash",line,[.00018+.00055*(1-u*u) for u in us],5)
    # A soft upper-lid crease sits well inside the orbital rim.
    fold=[]
    for u in us[1:-1]:
        x=center+.016*u
        y=outline(u)[1]+.0038*(1-u*u)
        fold.append((x,y,face_z(x,y)+.0021*(1-u*u)))
    cord(col,"lips",fold,[.00018+.00034*sin(pi*i/(len(fold)-1)) for i in range(len(fold))],5)
    # Brows thin at the temple. Give their lower and upper contours different arcs.
    rows=[[],[],[]]
    for j in range(19):
        t=j/18
        x=s*(.013+.045*t)
        y=1.623+.005*sin(pi*t)-.0015*t
        w=.00036+.0023*(sin(pi*t)**.52)*(1-.46*t)
        for row,dy,depth in zip(rows,(-w,0,w),(.0004,.0012,.0002)):
            row.append((x,y+dy,face_z(x,y+dy)+depth))
    patch(col,"brow",[r[::s] for r in rows])


def head(col):
    # Resolve most of the skull mesh across the face, with wider quads under the hair.
    angles=[-pi/2+pi*i/62 for i in range(62)]+[pi/2+pi*i/20 for i in range(20)]
    heights=sorted(set([round(1.504+.0028*i,5) for i in range(59)]+[r[0] for r in SKULL]))
    rows=[]
    for y in heights:
        w,f,b,off=sample(SKULL,y)
        row=[]
        for a in angles:
            x=w*sin(a)
            z=face_z(x,y) if cos(a)>=0 else off+b*power(cos(a),.92)
            row.append((x,y,z))
        rows.append(row)
    skull = rings(col,"sculpted head",rows,"complexion")
    # Adaptive tessellation keeps the nose and orbital relief dense and simplifies the vault.
    simplifier = skull.modifiers.new("Face tessellation", "DECIMATE")
    simplifier.ratio = .22
    # Local colour on the cheek, orbital rim, beard area and nose; in linear sRGB.
    m=M["complexion"].copy()
    m.name="face complexion"
    attr=m.node_tree.nodes.new("ShaderNodeVertexColor")
    attr.layer_name="Skin tone"
    m.node_tree.links.new(attr.outputs["Color"],m.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    skull.data.materials[0]=m
    colors=skull.data.color_attributes.new(name="Skin tone",type="FLOAT_COLOR",domain="POINT")
    base=Vector(gear.srgb(0xC98F70)[:3])
    warm=Vector(gear.srgb(0xC08168)[:3])
    stubble=Vector(gear.srgb(0xAE8876)[:3])
    for v,d in zip(skull.data.vertices,colors.data):
        x,back,y=v.co
        amount=bell(abs(x),y,.05,1.583,.029,.021)+.8*bell(x,y,0,1.574,.027,.012)
        color=base.lerp(warm,min(1,amount)*min(1,max(0,-back*16)))
        beard=.40*bell(x,y,0,1.523,.070,.023)+.25*bell(x,y,0,1.553,.026,.005)
        d.color=(*color.lerp(stubble,beard),1)
    for s in (-1,1):
        eyes(col,s)
        # Low relief nostril at the base of each ala, with the tip formed in the face mesh.
        pts=[]
        for i in range(9):
            t=i/8
            x=s*(.006+.010*t)
            y=1.567+.0014*sin(pi*t)+.0008*t
            pts.append((x,y,face_z(x,y)+.0005))
        cord(col,"lip_line",pts,[.0004+.0008*sin(pi*i/8) for i in range(9)],6)
        # Helix wraps around a recessed concha, tilted back at its upper attachment.
        oval(col,"complexion",(s*.079,1.593,-.004),(.011,.024,.014),16,10)
        oval(col,"lips",(s*.087,1.593,-.003),(.0035,.012,.0075),12,8)
        pts=[]
        for i in range(18):
            a=2*pi*i/17
            pts.append((s*(.086+.0018*cos(a)),1.594+.019*cos(a),-.004+.0105*sin(a)-.003*cos(a)))
        cord(col,"complexion",pts,.0025,7)
        cord(col,"complexion",[(s*.089,1.583,-.003),(s*.091,1.591,.001),
             (s*.090,1.597,-.002),(s*.088,1.603,-.006)],[.0017,.0022,.0019,.001],7)
    for upper in (False,True):
        rows=[]
        for j in range(4):
            row=[]
            t=j/3
            for i in range(21):
                u=(i-10)/10
                x=.026*u
                seam=1.5445+.0008*u*u-.0007*cos(2*pi*u)
                width=(1-u*u)*(.0038+.0024*math.exp(-((abs(u)-.24)/.18)**2) if upper else .0055)
                y=seam+(1 if upper else -1)*width*t
                z=face_z(x,y)+(1-u*u)*(.0013*(1-t)+.0024*sin(pi*t))+.00012
                row.append((x,y,z))
            rows.append(row)
        patch(col,"lips",rows if upper else rows[::-1])
    pts=[]
    for i in range(25):
        u=(i-12)/12
        x=.026*u
        y=1.5445+.0008*u*u-.0007*cos(2*pi*u)
        pts.append((x,y,face_z(x,y)+.0016*(1-u*u)+.00025))
    cord(col,"lip_line",pts,[.0002+.0006*(1-((i-12)/12)**2) for i in range(25)],5)
    # Close-cropped hairline is high over the ears and lower at the nape.
    rows=[]
    for j in range(6):
        row=[]
        for i in range(48):
            a=2*pi*i/48
            low=1.615+.035*cos(a)+.005*sin(a)**2-.010*math.exp(-((abs(sin(a))-.95)/.07)**2)*max(cos(a),0)*2
            y=low+(1.708-low)*j/5
            w,f,b,off=sample(SKULL,y)
            row.append(((w+.0018)*sin(a),y,off+(f+.002 if cos(a)>0 else b+.002)*power(cos(a),.82)))
        rows.append(row)
    rings(col,"short hair",rows,"hair")
    helmet(col,skull)


def helmet(col,skull):
    n=48
    def shell_row(h,w,d,overhang,tilt):
        row=[]
        for i in range(n):
            a=2*pi*i/n
            front=max(cos(a),0)
            row.append((w*sin(a),h-tilt*front**3,d*cos(a)+overhang*front**3))
        return row
    rings(col,"suspension band",[shell_row(*r) for r in [
        (1.637,.091,.106,.002,.001),(1.640,.093,.109,.002,.001),
        (1.65,.093,.109,.002,.001)]],"cuff")
    rings(col,"moulded peak",[shell_row(*r) for r in [
        (1.643,.092,.110,.006,.003),(1.645,.106,.118,.026,.005),
        (1.648,.110,.12,.031,.005),(1.651,.109,.119,.030,.005),
        (1.653,.099,.111,.010,.002)]],"helmet")
    crown=[shell_row(*r) for r in [
        (1.647,.099,.113,.003,.001),(1.655,.101,.114,.002,.001),
        (1.67,.100,.113,.002,.001),(1.692,.094,.108,0,0),(1.71,.084,.098,0,0),
        (1.726,.067,.081,0,0),(1.737,.046,.059,0,0),(1.744,.018,.027,0,0)]]
    for j,row in enumerate(crown):
        for i,(x,y,z) in enumerate(row):
            rib=math.exp(-(x/.019)**4)*max(0,min(1,(y-1.657)/.054))
            row[i]=(x,y+.007*rib,z*(1+.018*rib))
    rings(col,"helmet shell",crown,"helmet")
    for s in (-1,1):
        # Wide, flat webbing follows the cheeks and cups the underside of the chin.
        route=[(.095,1.65,.025),(.084,1.628,.028),(.08,1.603,.033),(.073,1.574,.041),
               (.063,1.548,.050),(.050,1.526,.056),(.037,1.517,.061),(.028,1.511,.064),
               (.016,1.505,.064),(.011,1.502,.064),(0,1.501,.064)]
        def web(path,width):
            rows=[]
            dense=[Vector(a).lerp(Vector(b),i/4) for a,b in zip(path,path[1:]) for i in range(4)]
            for x,y,z in [*dense,path[-1]]:
                row=[]
                for dz in (-width/2,0,width/2):
                    hit,loc,_,_=skull.ray_cast(B(s*.16,y,z+dz),B(-s,0,0))
                    xx=abs(loc.x)+.0018 if hit and y<1.644 else x
                    if y>1.61 and hit:
                        xx=max(xx,x)
                    row.append((s*xx,y,z+dz))
                rows.append(row)
            patch(col,"web_dark",rows)
        web(route,.010)
        web([(.093,1.644,-.041),(.085,1.614,-.035),(.078,1.587,-.022),
             (.072,1.566,.003),(.065,1.548,.046)],.008)
        hit,loc,_,_=skull.ray_cast(B(s*.16,1.549,.049),B(-s,0,0))
        if hit:
            oval(col,"plastic",(loc.x+s*.002,1.549,.049),(.003,.006,.0065),10,6)
        for j in range(3):
            z=-.044+j*.017
            x=.099*math.sqrt(1-(z/.115)**2)
            cord(col,"shell_edge",[(s*(x-.002),1.660,z-.005),(s*x,1.665,z),
                 (s*(x-.001),1.670,z+.005)],[.0008,.0018,.0007],6)



def empty(name,col):
    obj=bpy.data.objects.new(name,None)
    col.objects.link(obj)
    return obj


def fit_shoulder_strap(obj,surfaces,clearance):
    # Cast in each shoulder's sagittal plane, following the jacket continuously
    # from chest to back. Move both faces of each ribbon edge together.
    verts=obj.data.vertices
    for i in range(0,len(verts),4):
        for a,b in ((0,3),(1,2)):
            inner,outer=verts[i+a],verts[i+b]
            q=inner.co.copy()
            weight=max(0,min(1,(q.z-1.363)/.055))
            if not weight:
                continue
            radial=Vector((0,q.y,q.z-1.355)).normalized()
            offsets=[]
            for surface in surfaces:
                hit,p,_,_=surface.ray_cast(q+.25*radial,-radial)
                if hit:
                    offsets.append((p-q).dot(radial))
            if offsets:
                shift=radial*(max(offsets)+clearance)*weight
                inner.co+=shift
                outer.co+=shift
    obj.data.update()


def fit_workwear(vest,harness,leg_cols,parts):
    # Broad reflective bands follow both edges of the tapered vest. A straight
    # cylindrical band otherwise sinks into the fabric on the uphill edge.
    for obj in vest.objects:
        if obj.name.startswith("tape_band"):
            center=sum(v.co.z for v in obj.data.vertices)/len(obj.data.vertices)
            for v in obj.data.vertices:
                ratio=gear.body_r(v.co.z)/gear.body_r(center)
                v.co.x*=ratio
                v.co.y*=ratio
        elif obj.name.startswith("zip"):
            for v in obj.data.vertices:
                v.co.y-=.004
    for col in (vest,harness,*leg_cols.values()):
        for obj in col.objects:
            if not obj.data.vertices:
                continue
            if obj.name.startswith("Cube"):
                for face in obj.data.polygons:
                    face.use_smooth=False
            # Strap meshes are authored directly in rig space, hardware primitives
            # have their own transforms. The pads and hardware move together.
            if obj.location.length:
                if .96<obj.location.z<1.02:
                    obj.location.y*=.94
                continue
            if obj.name.startswith(("tape","shoulder","vest_shoulder","belt","leg_loop","web","subpelvic","back_pad")):
                obj.data.polygons.foreach_set("use_smooth",[True]*len(obj.data.polygons))
                obj.data.set_sharp_from_angle(angle=math.radians(48))
            for v in obj.data.vertices:
                y=v.co.z
                if col==harness:
                    v.co.y*=1-.06*math.exp(-((y-.99)/.05)**2)
                elif col==vest and obj.name.startswith("lathe") and y>1.28:
                    # Lower the side of the vest around the sleeve, retaining
                    # its distance to the body at the new armhole height.
                    radius=gear.body_r(y)
                    side=abs(v.co.x)/(radius*gear.SX*1.01)
                    t=max(0,min(1,(side-.64)/.36))
                    h=y-.77*(y-1.28)*t*t*(3-2*t)
                    scale=gear.body_r(h)/radius
                    v.co.x*=scale
                    v.co.y*=scale
                    v.co.z=h
            if obj.name.startswith("subpelvic"):
                side="L" if col==leg_cols[1] else "R"
                surfaces=[parts["drv_pelvis"],parts["drv_thigh_"+side],parts["drv_torso"]]
                verts=obj.data.vertices
                for i in range(0,len(verts),4):
                    # Each webbing station has two skin-side and two outer corners.
                    for inner,outer in [(verts[i],verts[i+3]),(verts[i+1],verts[i+2])]:
                        q=inner.co.copy()
                        depths=[]
                        for piece in surfaces:
                            start=Vector((q.x,.25,q.z))-piece.matrix_world.translation
                            hit,p,_,_=piece.ray_cast(start,Vector((0,-1,0)))
                            if hit:
                                depths.append(p.y+piece.matrix_world.translation.y)
                        if depths:
                            shift=max(depths)+.002-inner.co.y
                            inner.co.y+=shift
                            outer.co.y+=shift
    # Seat each layer on the finished surface below it, including wherever
    # the diagonal harness crosses the edge of the reflective tape.
    layers=[parts["drv_torso"],next(obj for obj in vest.objects if obj.name.startswith("lathe"))]
    for col,prefix,clearance in ((vest,"vest_shoulder",.002),(vest,"tape_shoulder",.001),
                                 (harness,"shoulder_strap",.004)):
        bpy.context.view_layer.update()
        ribbons=[obj for obj in col.objects if obj.name.startswith(prefix)]
        for obj in ribbons:
            fit_shoulder_strap(obj,layers,clearance)
        layers.extend(ribbons)


def finish(name, col, pivot, parent, target):
    """Bake modifiers, then join in joint-local axes. Keep the vest UV map."""
    bpy.ops.object.select_all(action="DESELECT")
    pieces=list(col.objects)
    for obj in pieces:
        bpy.context.view_layer.objects.active=obj
        for mod in list(obj.modifiers):
            bpy.ops.object.modifier_apply(modifier=mod.name)
        obj.select_set(True)
    origin=bpy.data.meshes.new(name)
    joint=gear.add_obj(name,origin,target)
    joint.location=B(*pivot)
    bpy.context.view_layer.objects.active=joint
    joint.select_set(True)
    bpy.ops.object.join()
    bpy.ops.object.material_slot_remove_unused()
    if name.startswith(("drv_boot", "drv_forearm")):
        simplifier = joint.modifiers.new("Workwear tessellation", "DECIMATE")
        simplifier.ratio = .69
        bpy.ops.object.modifier_apply(modifier=simplifier.name)
    joint.parent=parent
    joint.location=B(*pivot)-parent.matrix_world.translation
    bpy.context.view_layer.update()
    bpy.data.collections.remove(col)
    return joint


def build_driver():
    target=collection("Driver")
    rig=empty("rig",target)
    parts={}
    def assemble(name,col,pivot=(0,0,0),parent=rig):
        parts[name]=finish(name,col,pivot,parent,target)
        return parts[name]

    core=[collection(k) for k in ("pelvis pieces","jacket pieces","neck pieces")]
    body_core(*core)
    for key,col in zip(("pelvis","torso","neck"),core):
        assemble("drv_"+key,col)
    col=collection("head pieces")
    head(col)
    assemble("drv_head",col,(0,1.5,0))
    leg_cols={}
    for s,side in [(1,"_L"),(-1,"_R")]:
        thigh,shin,foot,upper,fore=[collection(k+side) for k in ("thigh","shin","boot","sleeve","forearm")]
        leg(s,thigh,shin)
        boot(s,foot)
        arm(s,upper,fore)
        hip=assemble("drv_thigh"+side,thigh,(s*.1,.92,0))
        knee=assemble("drv_shin"+side,shin,(s*.1,.48,0),hip)
        assemble("drv_boot"+side,foot,(s*.1,.08,0),knee)
        shoulder=assemble("drv_uparm"+side,upper,(s*.232,1.39,0))
        assemble("drv_forearm"+side,fore,(s*.232,1.09,0),shoulder)
        leg_cols[s]=collection("loop"+side)
    vest,harness=collection("vest pieces"),collection("harness pieces")
    gear.new_gear(0,vest,harness_col=harness,leg_cols=leg_cols,ring_steps=1)
    fit_workwear(vest,harness,leg_cols,parts)
    assemble("gear_vest",vest)
    assemble("gear_harness",harness)
    for s,side in [(1,"_L"),(-1,"_R")]:
        assemble("gear_legloop"+side,leg_cols[s],(s*.1,.92,0),parts["drv_thigh"+side])
    graph=bpy.context.evaluated_depsgraph_get()
    total=0
    for key,obj in parts.items():
        data=obj.evaluated_get(graph).data
        data.calc_loop_triangles()
        total+=len(data.loop_triangles)
        print(f"  {key}: {len(data.loop_triangles)} triangles")
    print(f"DRIVER: {total:,} triangles, {len(parts)} articulated mesh objects",flush=True)
    if total>30000:
        raise ValueError("Driver exceeds the 30,000 triangle budget")
    return rig,parts


def choose_device():
    try:
        prefs=bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX","HIP","CUDA","METAL","ONEAPI"):
            try:
                prefs.compute_device_type=backend
                prefs.refresh_devices()
            except (TypeError,RuntimeError):
                continue
            gpu=[d for d in prefs.devices if d.type==backend]
            if gpu:
                for d in prefs.devices:
                    d.use=d.type==backend
                scn.cycles.device="GPU"
                print("Cycles device:",backend,gpu[0].name,flush=True)
                return
    except Exception as err:
        print("Cycles device discovery:",err)
    scn.cycles.device="CPU"
    print("Cycles device: CPU",flush=True)


def studio():
    world=bpy.data.worlds.new("Courtyard daylight")
    world.use_nodes=True
    scn.world=world
    bg=world.node_tree.nodes["Background"]
    hdr=HERE/"assets"/"overcast_industrial_courtyard_2k.hdr"
    if hdr.exists():
        env=world.node_tree.nodes.new("ShaderNodeTexEnvironment")
        env.image=bpy.data.images.load(str(hdr))
        world.node_tree.links.new(env.outputs["Color"],bg.inputs["Color"])
        bg.inputs["Strength"].default_value=.65
    else:
        bg.inputs["Color"].default_value=(.65,.7,.8,1)
    sun=bpy.data.objects.new("Daylight",bpy.data.lights.new("Daylight","SUN"))
    scn.collection.objects.link(sun)
    sun.data.energy=2.0
    sun.data.angle=math.radians(14)
    sun.rotation_euler=tuple(map(math.radians,(48,-22,-20)))
    # Broad warm bounce brings out stitching and leaves a soft corneal highlight.
    light=bpy.data.lights.new("Daylight bounce","AREA")
    light.energy=42
    light.shape="DISK"
    light.size=1.55
    light.color=(1,.90,.80)
    card=bpy.data.objects.new(light.name,light)
    scn.collection.objects.link(card)
    card.location=B(-1.25,2.30,1.85)
    card.rotation_euler=(B(0,1.25,0)-card.location).to_track_quat("-Z","Y").to_euler()
    bpy.ops.mesh.primitive_plane_add(size=2000,location=(0,0,0))
    bpy.context.object.data.materials.append(gear.pm("warm grey floor",0x9A978F,.92))
    scn.render.engine="CYCLES"
    scn.cycles.samples=24
    scn.cycles.use_denoising=True
    scn.cycles.max_bounces=4
    scn.view_settings.view_transform="AgX"
    scn.view_settings.exposure=.3
    scn.render.image_settings.file_format="PNG"
    scn.render.resolution_percentage=100
    choose_device()
    cam=bpy.data.objects.new("Review camera",bpy.data.cameras.new("Review camera"))
    scn.collection.objects.link(cam)
    cam.data.type="ORTHO"
    scn.camera=cam
    return cam


def photograph(out,cam,name,target,direction,height,size):
    cam.location=B(*target)+B(*direction).normalized()*5
    cam.rotation_euler=(-B(*direction)).to_track_quat("-Z","Y").to_euler()
    width,pixels_high=size
    cam.data.ortho_scale=height*max(1,width/pixels_high)
    scn.render.resolution_x,scn.render.resolution_y=size
    path=out/("driver_"+name+".png")
    scn.render.filepath=str(path)
    t=time.perf_counter()
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as err:
        if scn.cycles.device=="CPU":
            raise
        print("GPU render failed, retrying on CPU:",err,flush=True)
        scn.cycles.device="CPU"
        bpy.ops.render.render(write_still=True)
    print(f"SHOT {path.name}: {time.perf_counter()-t:.1f}s on {scn.cycles.device}",flush=True)


def pose(parts,angles):
    for key,value in angles.items():
        parts["drv_"+key].rotation_euler=tuple(map(math.radians,value))
    bpy.context.view_layer.update()


def render_shots(out,rig,parts):
    out.mkdir(parents=True,exist_ok=True)
    # OptiX otherwise falls back to the process working directory on managed PCs.
    cache=HERE/"out"/"cycles_cache"
    cache.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault("OPTIX_CACHE_PATH",str(cache))
    cam=studio()
    old=collection("Current page figure")
    gear.body(0,old)
    gear.old_gear(0,old)
    # Offset along the camera's horizontal axis for equal scale and ground line.
    direction=(.52,.19,1)
    right=B(1,0,-.52).normalized()*.43
    for obj in old.objects:
        obj.location-=right
    rig.location=right
    photograph(out,cam,"compare",(0,.875,0),direction,1.98,(1080,920))
    old.hide_render=True
    rig.location=(0,0,0)
    for name,direction in [("front",(0,.105,1)),("back",(0,.105,-1)),("side",(1,.105,0))]:
        photograph(out,cam,name,(0,.875,0),direction,1.97,(660,940))
    pose(parts,{"thigh_R":(-40,0,0),"shin_R":(70,0,0),"uparm_L":(-90,0,0),
                "forearm_L":(-45,0,0),"head":(0,0,20)})
    photograph(out,cam,"pose",(0,.88,.08),(.73,.19,1),2.0,(760,940))
    pose(parts,{"uparm_L":(-68,0,0),"forearm_L":(-141,0,0),"head":(0,0,-3)})
    parts["drv_forearm_L"].rotation_euler.rotate_axis("Z",math.radians(106))
    scn.cycles.samples=36
    photograph(out,cam,"face",(.079,1.587,.028),(.41,.135,1),.41,(930,800))


def export_glb(path,rig,parts):
    """Web export: one node per joint segment, origins at the page's joints (see preview/index.html)."""
    # The fabric grain is a procedural noise the glTF exporter cannot carry: drop it so each
    # material exports its plain base colour instead of white.
    for mat in bpy.data.materials:
        if not mat.use_nodes: continue
        bsdf=mat.node_tree.nodes.get("Principled BSDF")
        if not bsdf: continue
        for name in ("Base Color","Normal"):
            inp=bsdf.inputs[name]
            for link in list(inp.links):
                if link.from_node.type in ("VALTORGB","BUMP"):
                    mat.node_tree.links.remove(link)
    for img in bpy.data.images:
        if img.size[0]>512: img.scale(512,max(1,img.size[1]*512//img.size[0]))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts.values(): obj.select_set(True)
    path.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(path),export_format="GLB",use_selection=True,export_apply=True,
        export_yup=True,export_cameras=False,export_lights=False,export_animations=False,
        export_draco_mesh_compression_enable=True,export_draco_mesh_compression_level=7,
        export_draco_position_quantization=14,export_draco_normal_quantization=10)
    print("EXPORTED",path,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shots",type=Path)
    parser.add_argument("--export",type=Path)
    opts=parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    rig,joints=build_driver()
    if opts.shots:
        render_shots(opts.shots.resolve(),rig,joints)
    if opts.export:
        export_glb(opts.export.resolve(),rig,joints)

