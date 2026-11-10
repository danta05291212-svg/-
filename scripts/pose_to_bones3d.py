#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pose_to_bones.py —— 用 3D 世界坐标复刻原片动作

为什么改用 world_landmarks：
    2D 投影分不清"手臂向前伸"和"向侧面张"——两者在画面上一模一样，
    换算出来的角度必然错。mediapipe 的 pose_world_landmarks 给的是
    以髋部为原点的米制 3D 坐标，才有深度信息。

坐标轴（实测）：
    y 向下为正（NOSE y≈-0.61 在头顶，ANK y≈+0.81 在脚下）
    x 人物左右，z 前后（朝相机为负）

角度定义：
    pitch = asin(-dy / |v|)   → 0 = 水平，+90 = 垂直向上，-90 = 垂直向下
"""

from __future__ import annotations

import json
import math
import os

SRC = r"E:\工作台\07-本地AI基建\deepseek harness\manga-studio"
POSE = r"D:\tmp\mp\pose3d.json"

NOSE = 0
L_SHO, R_SHO = 11, 12
L_ELB, R_ELB = 13, 14
L_WRI, R_WRI = 15, 16
L_HIP, R_HIP = 23, 24
L_KNE, R_KNE = 25, 26
L_ANK, R_ANK = 27, 28

SAMPLE_EVERY = 3


def vec(a, b):
    return (b[0] - a[0], b[1] - a[1], b[2] - a[2])


def norm(v):
    m = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1e-6
    return (v[0] / m, v[1] / m, v[2] / m)


def pitch(v):
    """与水平面的夹角，向上为正。（y 向下为正，所以取负）"""
    n = norm(v)
    return math.degrees(math.asin(max(-1.0, min(1.0, -n[1]))))


def yaw(v):
    """左右偏摆，人物右手方向为正。"""
    n = norm(v)
    return math.degrees(math.atan2(n[0], -n[1] + 1e-6))


def clamp(v, lo=-170.0, hi=170.0):
    return max(lo, min(hi, v))


def convert(fr):
    w = fr.get("world")
    if not w:
        return None
    sho_l, sho_r = w[L_SHO], w[R_SHO]
    hip_l, hip_r = w[L_HIP], w[R_HIP]
    hip_mid = tuple((hip_l[i] + hip_r[i]) / 2 for i in range(3))
    sho_mid = tuple((sho_l[i] + sho_r[i]) / 2 for i in range(3))
    up = vec(hip_mid, sho_mid)          # 躯干向上向量

    out = {}
    torso_pitch = pitch(up) - 90.0      # 站立时 up 是竖直向上 → pitch=90
    out["Abdomen"] = [clamp(torso_pitch * 0.6), 0.0, 0.0]
    out["Torso"] = [0.0, 0.0, 0.0]
    out["Hips"] = [0.0, 0.0, 0.0]

    # 手臂：肩→肘 的 pitch（0=水平，+90=上举，-90=垂下）
    for side, (sho, elb, wri) in (
            ("R", (sho_r, w[R_ELB], w[R_WRI])),
            ("L", (sho_l, w[L_ELB], w[L_WRI]))):
        arm = vec(sho, elb)
        fore = vec(elb, wri)
        p_arm = pitch(arm)
        # 实测：UpperArm.X 正值向上（+90 垂直上举），0 是 T-pose，-60 是垂下
        out[f"UpperArm.{side}"] = [clamp(p_arm * 0.95), 0.0, 0.0]
        # 前臂相对上臂的弯折
        p_fore = pitch(fore)
        bend = clamp((p_fore - p_arm) * 0.8)
        out[f"LowerArm.{side}"] = [0.0, 0.0, clamp(bend)]

    # 腿：髋→膝 的 pitch（-90=垂直向下站直，0=抬到水平）
    for side, (hip, kne, ank) in (
            ("R", (hip_r, w[R_KNE], w[R_ANK])),
            ("L", (hip_l, w[L_KNE], w[L_ANK]))):
        thigh = vec(hip, kne)
        shin = vec(kne, ank)
        p_thigh = pitch(thigh)
        lift = clamp(p_thigh + 90.0)     # 站直=0，抬到水平=90
        out[f"UpperLeg.{side}"] = [lift, 0.0, 0.0]
        p_shin = pitch(shin)
        out[f"LowerLeg.{side}"] = [clamp((p_shin - p_thigh) * 0.7, -95.0, 45.0), 0.0, 0.0]

    return out


def main():
    with open(POSE, encoding="utf-8") as fh:
        data = json.load(fh)
    frames = data["frames"]
    fps = data.get("fps") or 30

    beats = []
    for fr in frames[::SAMPLE_EVERY]:
        bones = convert(fr)
        if bones is None:
            continue
        beats.append({"at": fr["f"] + 1, "root": [0.0, 0.0, 0.0],
                      "turn": 0.0, "bones": bones})

    total = int(round(len(frames) / fps * 24))
    print(f"frames {len(frames)} -> beats {len(beats)} render_total {total}")

    scene = {
        "fps": 24, "frames": total, "resolution": [288, 512],
        "out_dir": "out/comic/dance_3d",
        "shots": [{
            "name": "REPLICA_3D", "lens": 35,
            "room": {"size": [12.0, 12.0, 3.4], "wall": "none"},
            "props": [{"loc": [0.0, 0.0, -0.02], "size": [9.0, 9.0, 0.04],
                       "color": [0.62, 0.60, 0.56]}],
            "engine": "workbench",
            "camera": {"keys": [
                {"frame": 1, "loc": [0.0, -3.30, 1.05], "target": [0.0, 0.0, 0.94]},
                {"frame": total, "loc": [0.0, -3.30, 1.05], "target": [0.0, 0.0, 0.94]}]},
            "actors": [{
                "role": "dancer", "archetype": "male_casual",
                "loc": [0.0, 0.0, 0.0], "rot": 0, "height": 1.72,
                "bone_poses": beats,
            }]
        }]
    }
    out = os.path.join(SRC, "comic", "scripts", "shots-dance-3d.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(scene, fh, ensure_ascii=False, indent=2)
    print("written", out)


if __name__ == "__main__":
    main()
