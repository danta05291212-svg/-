import cv2, json, os, sys
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mpp
from mediapipe.tasks.python import vision

# mediapipe 的 C++ 层不认中文路径，输入输出都放纯 ASCII 目录
VID = r"D:\tmp\mp\ref.mp4"
MODEL = r"D:\tmp\mp\pose.task"
OUT = r"D:\tmp\mp\pose3d.json"
LIMIT = int(os.environ.get("MP_LIMIT", "0"))

cap = cv2.VideoCapture(VID)
fps = cap.get(cv2.CAP_PROP_FPS) or 30
n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print("VIDEO", n, round(fps, 2), "fps")

opts = vision.PoseLandmarkerOptions(
    base_options=mpp.BaseOptions(model_asset_path=MODEL),
    running_mode=vision.RunningMode.VIDEO,
    num_poses=1,
    min_pose_detection_confidence=0.3,
    min_pose_presence_confidence=0.3,
    min_tracking_confidence=0.3,
)
land = vision.PoseLandmarker.create_from_options(opts)

frames = []
i = 0
w = h = 0
nworld = 0
while True:
    if LIMIT and i >= LIMIT:
        break
    ok, img = cap.read()
    if not ok:
        break
    h, w = img.shape[:2]
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    mpimg = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    res = land.detect_for_video(mpimg, int(i * 1000 / fps))
    rec = {"f": i, "t": round(i / fps, 3), "pts": None, "world": None}
    if res.pose_landmarks:
        rec["pts"] = [[round(p.x, 4), round(p.y, 4), round(p.z, 4),
                       round(getattr(p, "visibility", 0.0) or 0.0, 3)]
                      for p in res.pose_landmarks[0]]
    wl = getattr(res, "pose_world_landmarks", None)
    if wl:
        rec["world"] = [[round(p.x, 5), round(p.y, 5), round(p.z, 5)] for p in wl[0]]
        nworld += 1
    frames.append(rec)
    i += 1
    if i % 50 == 0:
        print("...", i, "world", nworld, flush=True)

land.close()
cap.release()
hit = sum(1 for f in frames if f["pts"])
print("EXTRACTED", len(frames), "pose", hit, "world", nworld, "size", w, h)
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump({"fps": fps, "w": w, "h": h, "frames": frames}, fh)
print("DONE", OUT)
