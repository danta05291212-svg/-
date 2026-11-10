---
name: video-to-blockout
description: "把任意真人视频里的动作转成白模动画的完整流程：抓片（抖音 CDP / B站 yt-dlp / 本地片源）→ ExMR 出 SMPL-X 参数和 BVH（HF Space 或本地 RGB MoCap）→ smplx 包算顶点 → Blender shape key 渲染。含五条实测错路（MediaPipe 2D、重定向、中文路径、BVH 参数、HF 额度误解）、长镜头分镜扫描法、暗光预处理。当用户要\"复刻某段视频的舞蹈/动作\"\"从视频提取动作\"\"做动作白模\"\"视频转 BVH\"\"动作迁移的参考视频\"\"复刻长镜头\"时使用。"
---

# 视频 → 动作 → 白模（video to blockout）

把任意一段真人视频里的动作，转成可渲染的白模动画。全程用公开工具，不需要动捕设备。

**这条链路的定位**：动作交给 3D 动捕模型，外形交给 SMPL-X 网格，两者天生匹配，**不做重定向**。

---

## 0. 一句话流程

```
参考视频（抖音 CDP / B站 yt-dlp / 本地片源）
  → ExMR（HF Space 或本地 RGB MoCap）→ SMPL-X 参数 + BVH
  → smplx 包算顶点序列
  → Blender 建网格 + shape key → 白模视频
```

**两条执行路径，按场景选**：

| 场景 | 用哪条 | 理由 |
|---|---|---|
| 一次性的短片段（< 30 秒）| **HF Space**（`twehrbein/ExMR`）| 零安装，3-5 分钟出结果 |
| 反复跑 / 多角色 / 长视频 | **本地 RGB MoCap** | HF 额度按账号算，一天跑不了几次；本地一次装好永久用 |
| 需要导出 FBX / 重定向到人形 | **本地 RGB MoCap** | 内置 humanoid retargeting + FBX/VMD 导出 |

---

## 1. 拿到参考视频（如果来源是抖音）

抖音的三个解析 API 全部失效（`tikwm` 解析失败、`douyin.wtf` 404、`xingzhige` 源异常），网页版用 MSE 播放也抓不到直链。

**唯一可行**：headless Edge + CDP 读 `video.currentSrc`。

```bash
# 1) 短链解析出视频 ID
curl -sIL -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)" \
  "https://v.douyin.com/XXXXXX/" | grep -i location
# → https://www.iesdouyin.com/share/video/<AWEME_ID>/

# 2) 启动带调试端口的 headless Edge
msedge.exe --headless=new --disable-gpu --remote-debugging-port=9222 \
  --user-data-dir=<临时目录> about:blank &

# 3) Node 脚本（Node 22+ 自带 WebSocket）
#    Page.navigate → 等 10 秒 → 执行 video.play() → 再等 5 秒
#    → Runtime.evaluate 读 document.querySelector('video').currentSrc
#    → 用 fetch 下载（带 Referer: https://www.douyin.com/）
```

关键：URL 有时效签名，**读到就立刻下载**。

其他平台用 yt-dlp 即可。

---

## 2. 视频 → 3D 动作（ExMR）

**不要用 MediaPipe**（原因见第 6 节）。

**[ExMR](https://github.com/twehrbein/ExMR)** 的 HuggingFace Space：`twehrbein/ExMR`

```python
from gradio_client import Client, handle_file
c = Client('twehrbein/ExMR')
r = c.predict(
    video=handle_file(r'D:\tmp\mp\ref.mp4'),
    static_cam=True,      # 固定机位
    snap_to_ground=True,  # 脚贴地
    smoothing='both',
    fps30=False,
    start_time=0, end_time=24.8,
    api_name='/reconstruct')
# r[0] = 可视化 mp4
# r[1] = [results.npz, amass.npz, <name>.bvh]
```

**输出**：
| 文件 | 内容 |
|---|---|
| `<name>.bvh` | 55 关节 SMPL-X 骨架，厘米、y up |
| `<name>_results.npz` | `smplx_global_body_pose`(N,63)、`betas`(N,10)、`global_orient`(N,3)、`transl`(N,3)、`joints_global`(N,76,3)、`fps` |
| `<name>_amass.npz` | AMASS 格式 |

**注意**：HF 的 ZeroGPU 配额是**账号级**的，不是按 Space 算——ExMR 和 MoCapAnything 共用同一个额度池（实测：ExMR 跑完，MoCapAnything 立刻报同一个错）。用光了要么等一天，要么挂 HF token 提额。

### 2b. 本地部署（推荐长期用）

ExMR 官方**不支持 Windows 原生**（README 明说要用 WSL2）。Windows 上的正解是社区应用：

**[`toyxyz/RGBMocap`](https://github.com/toyxyz/toyxyz_RGBMocap)**（1219 stars，ExMR README 里唯一点名的 Windows 方案）

```cmd
git clone https://github.com/toyxyz/toyxyz_RGBMocap.git
cd toyxyz_RGBMocap
install.cmd      :: 下 Python 环境 + Blender 4.5 + FFmpeg + 依赖，约 7.1 GB
RGBMoCap.cmd     :: 启动 GUI，模型在 Model Manager 里下
```

**它比 HF Space 多出来的能力**：

| 能力 | 说明 |
|---|---|
| ExMR / FlowHMR / GVHMR 三选一 | 不同模型对暗光/遮挡的鲁棒性不同 |
| **humanoid retargeting** | SMPL-X → 任意人形骨架，**这是手写重定向搞不定的** |
| 脚部接触修正 | contact correction，治滑步/悬浮 |
| FBX / VMD 导出 | 直接进 Blender / Unity / UE |

**安装坑**：
- 用 `Start-Process cmd.exe -ArgumentList '/c','install.cmd'` 跑（直接 `cmd /c install.cmd` 会因为 `pause` 卡住）
- 路径必须是 Windows 反斜杠，`D:/tmp/...` 会被 cmd 拆坏
- 总下载 **7.1 GB**，直连 PyPI 约 1 MB/s，40-90 分钟

**模型权重可直接下（不用 GUI）**：
```
https://hf-mirror.com/twehrbein/ExMR/resolve/main/exmr.safetensors          225 MB
https://hf-mirror.com/twehrbein/ExMR/resolve/main/rtmw-x_384x288_fp16.onnx  176 MB
```

---

## 2c. 长镜头怎么找人（分镜扫描法）

长镜头（比如真探那 6 分钟）里有十几个角色，但 ExMR 是**单人重建**——必须先按角色切段。

**扫描法**：每 20 秒抽一帧，拼成一张表，逐帧标注内容：

```bash
for t in $(seq 0 20 380); do
  ffmpeg -y -v error -ss $t -i core6min.mp4 -frames:v 1 "scan_$(printf %03d $t).png"
done
# 拼图时把秒数写在每格下面
```

按这张表挑出「单人 + 光线够 + 动作明确」的段，每段 20-30 秒单独跑 ExMR。

**真探 S1E4 实测结果**（供参考）：整段 683 秒，能用的只有 4 段（100s 特写、140s 门口、200s 院子、340s 车内），其余太暗或多人。

### 暗光预处理（必做）

夜戏/暗场直接喂 ExMR 会大面积丢人。先提亮：

```bash
ffmpeg -i dark.mp4 -vf "eq=brightness=0.18:contrast=1.35:saturation=1.1" -c:v libx264 -crf 20 bright.mp4
```

提亮只用于**动作提取**，最终白模输出用原始参数（提亮不影响 SMPL-X 参数）。

---

## 3. 参数 → 顶点序列（comfyui 的 Python）

Blender 自带的 Python **没有 torch/smplx**，所以这一步必须用外部 Python。

```bash
pip install smplx torch
```

```python
import numpy as np, torch, smplx
d = np.load('ref_results.npz')
pose   = d['smplx_global_body_pose']
betas  = d['smplx_global_betas']
orient = d['smplx_global_global_orient']
transl = d['smplx_global_transl']
n = len(pose)

body = smplx.create('SMPLX_NEUTRAL.npz', model_type='smplx', gender='neutral',
                    use_pca=False, flat_hand_mean=True, batch_size=n)
with torch.no_grad():
    out = body(betas=torch.tensor(np.repeat(betas[:1], n, axis=0), dtype=torch.float32),
               body_pose=torch.tensor(pose, dtype=torch.float32),
               global_orient=torch.tensor(orient, dtype=torch.float32),
               transl=torch.tensor(transl, dtype=torch.float32))
v = out.vertices.numpy()          # (n, 10475, 3)
np.savez_compressed('verts.npz', verts=v, faces=body.faces.astype(np.int32), fps=d['fps'])
```

**SMPL-X 模型文件**（官网要登录，用公开镜像）：
```
https://hf-mirror.com/camenduru/show-dataset/resolve/main/SMPLX_NEUTRAL.npz
size 167264530
sha256 bdf06146e27d92022fe5dadad3b9203373f6879eca8e4d8235359ee3ec6a5a74
```

---

## 4. 顶点 → Blender 白模

```python
import bpy, numpy as np, math
d = np.load('verts.npz'); verts, faces = d['verts'], d['faces']

mesh = bpy.data.meshes.new('body')
mesh.from_pydata(verts[0].tolist(), [], faces.tolist()); mesh.update()
ob = bpy.data.objects.new('body', mesh)
bpy.context.collection.objects.link(ob)

# 每 2 帧一个 shape key（600 → 300，够顺滑又不爆内存）
ob.shape_key_add(name='Basis')
for i in range(2, len(verts), 2):
    kb = ob.shape_key_add(name=f'f{i}')
    kb.data.foreach_set('co', verts[i].flatten())

ob.rotation_euler = (math.radians(90), 0, 0)   # SMPL 是 y-up，Blender 是 z-up
```

渲染（Workbench 最快）：

```python
sc.render.engine = 'BLENDER_WORKBENCH'
sc.render.resolution_x, sc.render.resolution_y = 288, 512   # 竖屏
sc.display.shading.light = 'STUDIO'
sc.display.shading.color_type = 'SINGLE'
sc.display.shading.single_color = (0.82, 0.80, 0.78)
# 相机：按首帧包围盒算，距离 = H * 2.3，看向中心
```

逐帧切换 key block 的 `value`，渲一张一张 PNG，最后 `ffmpeg -framerate 15 -i "img_%04d.png"` 合成。

---

## 5. 验收（必做）

**并排对比图**，左原片右复刻，同一时间点：

```python
ref_frames = {t: 原片抽帧}
rep_frames = {t: 复刻抽帧}
for t in times: 并排放进一张图 + 标注时间
```

逐条列出**差异**（哪个时间点哪个关节差多少），不要自己说“像”。

关键判据：
- 抬膝：膝盖是否高过髋部
- 上举：手腕是否高过头部
- 转身：肩线朝向是否变化
- 节奏：动作起止时间点是否对齐

---

## 6. 五条错路（都实测过，别再走）

### ❌ MediaPipe 2D/3D 关键点 + 手写角度映射
- 2D 投影分不清"手臂前伸"和"向侧面张"
- 遮挡的腿直接检测不到（抬膝那帧两条膝盖都在髋下方 → 判不出"抬了"）
- 从 2D 反推 3D 角度是病态问题，手调 6 轮不收敛

### ❌ 重定向（BVH → 别人的骨架）
- SMPL-X 和 Quaternius 的层级结构完全不同（`pelvis→spine1/2/3` vs `Hips→Abdomen→Torso`）
- 试过：local copy rotation + rest 补偿、world copy transforms、自动权重、包络权重——全部失败（人压扁、网格撕裂、动作静止）
- **正解是不重定向**：直接用 SMPL-X 自己的骨架 + 自己的网格
- 真要重定向，用 RGB MoCap 的内置 humanoid retargeting，别手写

### ❌ 用 MediaPipe 跑中文路径
mediapipe 的 C++ 层不认中文路径，模型和视频都要复制到 `D:\tmp\mp\` 这类纯 ASCII 目录。

### ❌ BVH 导入参数瞎猜
Blender 4.5 的 `bpy.ops.import_anim.bvh(filepath=..., global_scale=0.01)` **没有** `use_fps` / `update_scene_fps` 参数。

### ❌ 以为换个 HF Space 就有额度
ZeroGPU 配额是**账号级**的。ExMR 跑满之后，MoCapAnything 会立刻报同一个错（`You have exceeded your ZeroGPU runs limit`），换 Space 没用。

---

## 6b. 找片源的两个坑

**B站有同名陷阱**：搜"真探"出来的"真探1 全集合集"可能是**同名游戏实况**，不是美剧。下之前先 `yt-dlp --skip-download --print "%(title)s|%(duration)s"` 核对时长（剧集单集 40+ 分钟，游戏实况分 P 很短）。

**YouTube 的影视片段基本都被版权方封**：真探的长镜头 `s_HuFuKiq8U` 报 `blocked due to the claimed content by Home Box Office Inc.`，另一个 `eVK_scFlCHg` 是私有视频。影视内容优先找**本地片源**或问用户要。

**从整集里定位长镜头**：影视剧的长镜头通常在**集末**。用 `ffprobe` 拿到总时长，从 `总时长 - 700 秒` 开始每 20 秒抽帧扫一遍。

---

## 7. 已知限制

| 项 | 说明 |
|---|---|
| 体型 | `SMPLX_NEUTRAL` 是中性，偏男性化；要贴原片女性用 `SMPLX_FEMALE.npz`（官方 zip 里也有） |
| 手指 | ExMR 输出含手部参数，但 `flat_hand_mean=True` 时手指是平的 |
| 表情 | 不含面部（jaw/eyes 不动） |
| 单人 | ExMR 一次只重建画面里最主要的一个人，**多人场景必须先按角色切段** |
| 暗光 | 夜戏直接跑会丢人，先做提亮预处理（见 2c） |
| 长视频 | HF 一次跑 25 秒没问题；本地 RGB MoCap 可跑更长，但显存要够（1080×1920 视频峰值 7.4 GB） |
| 内存 | 600 帧 × 10475 顶点 × 3 = 约 190 MB，shape key 全建会到 1 GB 量级 |

---

## 8. 文件产物

```
assets/ref/xxx.mp4          原片
D:/tmp/mp/exmr/ref.bvh      SMPL-X 骨架动画
D:/tmp/mp/exmr/ref_results.npz   SMPL-X 参数（600 帧）
D:/tmp/mp/exmr/verts.npz    顶点序列（600×10475×3）
out/comic/smplx/dancer.mp4  白模视频
out/comic/_compare/*.png    并排对比图
```

---

## 9. 这套白模能干什么

**它是给 AI 视频模型的“动作参考”**，不是成品。

```
白模视频（动作准）
  + 角色图（长什么样）
  + 场景图（在哪）
  → Seedance 动作迁移
  → 成品
```

Seedance 的硬约束（实测）：`reference_video` 必须是公网 URL、像素 ≥407696（960×540 起）、图床用 `pomf2.lain.la`。
