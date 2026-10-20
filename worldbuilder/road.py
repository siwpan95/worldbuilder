"""公路走廊：把一条路"挖"进分形地形（世界builder 的道路能力补齐）。

与 ``terrain.py`` 的关系：``terrain.generate_heightmap`` 生成自然地表；
本模块在其上叠加**人工走廊**——公路路基压平、路侧过渡带、可选的远山背景。
产物仍是高度图 + 沿线采样函数，供渲染端（如 3dworld 的 heightfield builder）
直接消费。

设计要点（实测踩坑）：
- 路面高程必须与渲染端的路面网格一致：``corridor_level(hm_value) * height``
  就是世界 y，两边要引用同一个常量，否则路会被地形埋住；
- 走廊边缘用 smoothstep 过渡，硬切会产生锯齿法线（低分辨率高度图尤其明显）；
- ``sample_height`` 提供双线性采样，供碎石/植被/里程碑"贴地"。
"""
from __future__ import annotations

import numpy as np

from .noise import fractal_noise

# 与示例场景一致的默认参数（戈壁公路：走廊压平 + 远山剪影）
DEFAULT_ROAD_HALF = 2.6        # 路面半宽（世界单位）
DEFAULT_SHOULDER = 3.0         # 路侧过渡带宽度
DEFAULT_FAR_START = 0.45       # 远山起始（|z| 归一化位置）
DEFAULT_FAR_GAIN = 1.9         # 远山增益


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def gobi_corridor(rows=96, cols=96, extent=40.0, seed=0,
                  base_scale=0.06, base_gain=0.18,
                  detail_scale=0.35, detail_gain=0.05,
                  road_half=DEFAULT_ROAD_HALF, shoulder=DEFAULT_SHOULDER,
                  far_start=DEFAULT_FAR_START, far_gain=DEFAULT_FAR_GAIN,
                  corridor_level=0.30, road_axis='x'):
    """戈壁公路走廊高度图。

    返回 ``(hm, coords_x, coords_z)``：``hm[row][col]``（row 对应 z 轴），
    取值 0..1+（远山可能 >1，交给渲染端的 height 映射与钳制）。

    ``road_axis='x'`` 表示路沿 x 方向延伸（走廊在 z≈0）；``'z'`` 则相反。
    """
    xs = np.linspace(-extent, extent, cols)
    zs = np.linspace(-extent, extent, rows)
    xm, zm = np.meshgrid(xs, zs)
    along, across = (xm, zm) if road_axis == 'x' else (zm, xm)

    base = fractal_noise(xm * base_scale, zm * base_scale,
                         octaves=4, seed=seed) * base_gain
    detail = fractal_noise(xm * detail_scale, zm * detail_scale,
                           octaves=3, seed=seed + 1) * detail_gain
    far_n = np.clip((np.abs(across) / extent) - far_start, 0, 1)
    ridged = 1.0 - np.abs(fractal_noise(xm * 0.045, zm * 0.045,
                                        octaves=3, seed=seed + 2) * 2.0 - 1.0)
    mountains = far_n ** 1.6 * ridged * far_gain
    hm = base + detail + mountains

    # 走廊压平 + smoothstep 过渡
    t = np.clip((np.abs(across) - road_half) / max(1e-6, shoulder), 0, 1)
    hm = hm * smoothstep(t) + corridor_level * (1.0 - smoothstep(t))
    return hm.astype(np.float32), xs, zs


def sample_height(hm, x, z, extent=40.0, height=1.0, y_base=0.0):
    """世界坐标 -> 地形高度（双线性），供道具贴地。"""
    rows, cols = hm.shape
    c = np.clip((x + extent) / (2 * extent) * (cols - 1), 0, cols - 1.001)
    r = np.clip((z + extent) / (2 * extent) * (rows - 1), 0, rows - 1.001)
    c0, r0 = int(c), int(r)
    fc, fr = c - c0, r - r0
    v = (hm[r0, c0] * (1 - fc) * (1 - fr) + hm[r0, c0 + 1] * fc * (1 - fr)
         + hm[r0 + 1, c0] * (1 - fc) * fr + hm[r0 + 1, c0 + 1] * fc * fr)
    return float(v) * height + y_base
