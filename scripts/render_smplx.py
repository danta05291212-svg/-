import bpy, os, math
import numpy as np

NPZ = r"D:\tmp\mp\exmr\verts.npz"
OUT = r"E:\工作台\07-本地AI基建\deepseek harness\manga-studio\tmp"

d = np.load(NPZ)
verts = d["verts"]           # (N, 10475, 3) y-up
faces = d["faces"]
N = verts.shape[0]
print("frames", N, "verts", verts.shape, "faces", faces.shape)

bpy.ops.wm.read_factory_settings(use_empty=True)
mesh = bpy.data.meshes.new("body")
mesh.from_pydata(verts[0].tolist(), [], faces.tolist())
mesh.update()
ob = bpy.data.objects.new("body", mesh)
bpy.context.collection.objects.link(ob)
mat = bpy.data.materials.new("skin"); mat.use_nodes = True
b = mat.node_tree.nodes.get("Principled BSDF")
if b:
    b.inputs["Base Color"].default_value = (0.80, 0.76, 0.72, 1)
    b.inputs["Roughness"].default_value = 0.9
ob.data.materials.append(mat)

# 每 2 帧一个 shape key（600 → 300 个，足够顺滑又不爆内存）
step = 2
idx = list(range(0, N, step))
ob.shape_key_add(name="Basis")
for i in idx[1:]:
    kb = ob.shape_key_add(name=f"f{i}")
    kb.data.foreach_set("co", verts[i].flatten())
print("shape keys", len(ob.data.shape_keys.key_blocks))

# SMPL 是 y-up → 绕 X 转 90° 变 z-up
ob.rotation_euler = (math.radians(90), 0, 0)
bpy.context.view_layer.update()
bb = [ob.matrix_world @ v.co for v in [ob.data.vertices[i] for i in range(0, len(ob.data.vertices), 500)]]
zs = [p.z for p in bb]; xs = [p.x for p in bb]; ys = [p.y for p in bb]
H = max(zs) - min(zs)
cx = (max(xs)+min(xs))/2; cy = (max(ys)+min(ys))/2; cz = (max(zs)+min(zs))/2
print("H", round(H,2), "center", round(cx,2), round(cy,2), round(cz,2))

sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.render.resolution_x, sc.render.resolution_y = 288, 512
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "SINGLE"
sc.display.shading.single_color = (0.82, 0.80, 0.78)
cam_d = bpy.data.cameras.new("C"); cam_d.lens = 32
cam = bpy.data.objects.new("C", cam_d); bpy.context.collection.objects.link(cam)
cam.location = (cx, cy - H * 2.3, cz + H * 0.02)
cam.rotation_euler = (math.radians(90), 0, 0)
sc.camera = cam
bpy.ops.mesh.primitive_plane_add(size=H * 5, location=(cx, cy, min(zs) - 0.01))

keys = ob.data.shape_keys.key_blocks
img = 0
for k, kb in enumerate(keys):
    for j, other in enumerate(keys):
        other.value = 1.0 if j == k else 0.0
    sc.frame_set(k + 1)
    sc.render.filepath = os.path.join(OUT, f"_sm_{img:04d}.png")
    bpy.ops.render.render(write_still=True)
    img += 1
    if k % 30 == 0:
        print("key", k, flush=True)
print("DONE", img)
