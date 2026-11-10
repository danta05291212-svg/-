import numpy as np, os, sys
import torch
import smplx

NPZ = r"D:\tmp\mp\exmr\ref_results.npz"
MODEL = r"D:\tmp\mp\smplx\SMPLX_NEUTRAL.npz"
OUT = r"D:\tmp\mp\exmr\verts.npz"

d = np.load(NPZ)
pose = d.get("smplx_global_body_pose")
betas = d.get("smplx_global_betas")
orient = d.get("smplx_global_global_orient")
transl = d.get("smplx_global_transl")
fps = float(d["fps"]) if "fps" in d else 30.0
n = len(pose)
print("frames", n, "fps", fps, "pose", pose.shape)

body = smplx.create(MODEL, model_type="smplx", gender="neutral",
                    use_pca=False, flat_hand_mean=True, batch_size=n)
print("model built, faces", body.faces.shape)

with torch.no_grad():
    out = body(betas=torch.tensor(np.repeat(betas[:1], n, axis=0), dtype=torch.float32),
               body_pose=torch.tensor(pose, dtype=torch.float32),
               global_orient=torch.tensor(orient, dtype=torch.float32),
               transl=torch.tensor(transl, dtype=torch.float32))
v = out.vertices.numpy().astype(np.float32)
print("verts", v.shape)
np.savez_compressed(OUT, verts=v, faces=body.faces.astype(np.int32), fps=fps)
print("SAVED", OUT, os.path.getsize(OUT))
