# video-to-blockout

把一段真人视频里的动作，转成可渲染的 3D 白模动画。**不用动捕设备，不用重定向。**

```
参考视频  →  SMPL-X 参数  →  顶点序列  →  白模视频
```

## 这套东西解决什么

做 AI 视频（Seedance / 海螺 / 可灵）时，最缺的是**动作参考**：

- 用文字描述"她转了个身"，模型给你一个含糊的扭动
- 用白模视频当 `reference_video`，模型会**照着动作复刻**

这个仓库就是把"任意视频里的动作"变成"能当参考的白模"。

## 核心思路

**动作交给 3D 动捕模型，外形交给 SMPL-X 网格，两者天生匹配。**

不要试图把动作"重定向"到别的角色骨架上——两套骨架的层级、父子关系、坐标轴朝向全不一样，手写必然失败（试过 4 种方法，全部压扁或撕裂）。

## 快速开始

### 1. 视频 → SMPL-X 参数

用 [ExMR](https://github.com/twehrbein/ExMR) 的 HuggingFace Space，零安装：

```python
from gradio_client import Client, handle_file

c = Client('twehrbein/ExMR')
r = c.predict(
    video=handle_file('ref.mp4'),
    static_cam=True, snap_to_ground=True,
    smoothing='both', fps30=False,
    start_time=0, end_time=24.8,
    api_name='/reconstruct')
# r[1] = [results.npz, amass.npz, <name>.bvh]
```

输出 `results.npz` 里是关键参数：
```
smplx_global_body_pose  (N, 63)   21 关节 × 3
smplx_global_betas      (N, 10)   体型
smplx_global_global_orient (N, 3) 根旋转
smplx_global_transl     (N, 3)    根位移
joints_global           (N, 76, 3) 76 个关节的 3D 世界坐标
```

### 2. 参数 → 顶点

```bash
pip install smplx torch
python scripts/smplx_verts.py
```

需要 SMPL-X 模型文件（官网注册免费下载，或用公开镜像，见 `SKILL.md`）。

### 3. 顶点 → 白模

```bash
blender -b -P scripts/render_smplx.py
```

输出 288×512 竖屏或任意分辨率的白模帧序列。

## 本地部署（长期用）

ExMR 官方**不支持 Windows 原生**。Windows 上的正解是社区应用 [`toyxyz/RGBMocap`](https://github.com/toyxyz/toyxyz_RGBMocap)，带 humanoid 重定向和 FBX 导出。

详见 `SKILL.md` 第 2b 节。

## 完整文档

[`SKILL.md`](./SKILL.md) — 320 行，包含：

- 抖音抓片（headless Edge + CDP 读 `video.currentSrc`）
- ExMR 两条路径（HF Space / 本地 RGB MoCap）
- 长镜头分镜扫描法（每 20 秒抽帧标注）
- 暗光预处理（夜戏必做）
- **五条实测错路**（MediaPipe 2D、重定向、中文路径、BVH 参数、HF 额度误解）
- 验收方法（并排对比 + 逐条列差异，禁止自评"像不像"）

## 已知限制

| 项 | 说明 |
|---|---|
| 单人 | ExMR 一次只重建最显眼的一个人，多人场景必须先按角色切段 |
| 暗光 | 夜戏直接跑会丢人，先提亮预处理 |
| 手指 | `flat_hand_mean=True` 时手指是平的 |
| 表情 | 不含面部 |

## 依赖的开源项目

| 项目 | 用途 |
|---|---|
| [ExMR](https://github.com/twehrbein/ExMR) | 单目视频 → SMPL-X 参数 + BVH |
| [SMPL-X](https://smpl-x.is.tue.mpg.de/) | 人体模型（需注册） |
| [RGB MoCap](https://github.com/toyxyz/toyxyz_RGBMocap) | Windows 本地 GUI |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 视频下载 |
| [Blender](https://www.blender.org/) | 渲染 |

## License

文档与脚本：MIT。
SMPL-X 模型：遵循其官方许可（非商用需注册）。
ExMR 模型权重：遵循其仓库许可。
