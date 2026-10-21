"""噪声生成：value / perlin / fractal，返回 0..1 的 numpy 数组。

所有函数输入 x, y（标量或同形数组），返回同形数组。
seed 控制可复现性。
"""
from __future__ import annotations

import warnings

import numpy as np


def _hash2(ix, iy, seed):
    """整数格点 -> 确定性伪随机 [0,1)。支持数组输入。"""
    ix = np.asarray(ix, dtype=np.int64)
    iy = np.asarray(iy, dtype=np.int64)
    h = ix * 374761393 + iy * 668265263 + np.int64(seed) * 1013904223
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h.astype(np.int64) & 0x7FFFFFFF).astype(np.float64) / 0x7FFFFFFF


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


# 2D 梯度噪声理论最大投影幅度（√(xf²+yf²) 在角点最大 ≈ √2/2）
_PERLIN_NORM = np.sqrt(2.0) / 2.0


def _lerp(a, b, t):
    return a + t * (b - a)


def value_noise(x, y, seed: int = 0) -> np.ndarray:
    """值噪声：格点随机值 + 平滑插值，返回 0..1。"""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    xi = np.floor(x).astype(np.int64)
    yi = np.floor(y).astype(np.int64)
    xf = x - xi
    yf = y - yi
    v00 = _hash2(xi, yi, seed)
    v10 = _hash2(xi + 1, yi, seed)
    v01 = _hash2(xi, yi + 1, seed)
    v11 = _hash2(xi + 1, yi + 1, seed)
    u = _smooth(xf)
    v = _smooth(yf)
    return _lerp(_lerp(v00, v10, u), _lerp(v01, v11, u), v)


def perlin_noise(x, y, seed: int = 0) -> np.ndarray:
    """Perlin 梯度噪声（基于格点角度梯度），返回 0..1。

    注意：若输入坐标全部落在**整数格点**上（小数部分 xf=yf=0，四角点积全为 0），
    输出将恒为 0.5（高程场被抹平）——这是数学必然，非 bug。生成地形请按波长
    缩放坐标（如 ``x * freq``，``freq = 1/波长``）以避开整点；检测到整点网格时
    会发出 ``UserWarning``。
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if np.all(x == np.floor(x)) and np.all(y == np.floor(y)):
        warnings.warn(
            "perlin/fbm 输入全部落在整数格点上，输出恒为 0.5（地形细节被抹平）；"
            "请按波长缩放坐标（如 x*freq，freq=1/波长）避开整点。",
            UserWarning, stacklevel=2)
    xi = np.floor(x).astype(np.int64)
    yi = np.floor(y).astype(np.int64)
    xf = x - xi
    yf = y - yi
    ang00 = _hash2(xi, yi, seed) * 2.0 * np.pi
    ang10 = _hash2(xi + 1, yi, seed) * 2.0 * np.pi
    ang01 = _hash2(xi, yi + 1, seed) * 2.0 * np.pi
    ang11 = _hash2(xi + 1, yi + 1, seed) * 2.0 * np.pi
    gx00, gy00 = np.cos(ang00), np.sin(ang00)
    gx10, gy10 = np.cos(ang10), np.sin(ang10)
    gx01, gy01 = np.cos(ang01), np.sin(ang01)
    gx11, gy11 = np.cos(ang11), np.sin(ang11)
    d00 = gx00 * xf + gy00 * yf
    d10 = gx10 * (xf - 1) + gy10 * yf
    d01 = gx01 * xf + gy01 * (yf - 1)
    d11 = gx11 * (xf - 1) + gy11 * (yf - 1)
    u = _smooth(xf)
    v = _smooth(yf)
    n = _lerp(_lerp(d00, d10, u), _lerp(d01, d11, u), v)
    # 按理论最大幅度归一化，使输出能覆盖完整 0..1 区间（提升对比度）
    return np.clip((n / _PERLIN_NORM + 1.0) / 2.0, 0.0, 1.0)


def fbm(x, y, octaves: int = 4, lacunarity: float = 2.0, gain: float = 0.5,
        seed: int = 0) -> np.ndarray:
    """分形布朗运动（fBm）：多层 perlin 叠加，返回 0..1。

    注意：整数格点输入会使输出恒为 0.5（详见 perlin_noise）；请按波长缩放坐标避开整点。

    参数：
        octaves:    叠加层数（默认 4）
        lacunarity: 每层频率倍增（默认 2.0）
        gain:       每层振幅衰减（默认 0.5）
        seed:       随机种子
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    total = np.zeros_like(x, dtype=np.float64)
    amp = 1.0
    freq = 1.0
    maxv = 0.0
    for o in range(octaves):
        total += amp * perlin_noise(x * freq, y * freq, seed=seed + o)
        maxv += amp
        amp *= gain
        freq *= lacunarity
    return np.clip(total / maxv, 0.0, 1.0)


def fractal_noise(x, y, octaves: int = 4, seed: int = 0) -> np.ndarray:
    """分形噪声：fBm 的便捷封装（默认 lacunarity=2.0 / gain=0.5）。

    示例：
        xs, ys = np.meshgrid(np.arange(64), np.arange(64))
        hm = fractal_noise(xs, ys, octaves=5, seed=1)
    """
    return fbm(x, y, octaves=octaves, lacunarity=2.0, gain=0.5, seed=seed)


# ---- Simplex 噪声（Perlin 的改进：方向伪影更少、计算更快）----
def _perm_table(seed):
    """由 seed 生成长度 512 的排列表（0..255 洗牌后复制）。"""
    rng = np.random.RandomState(seed)
    p = np.arange(256, dtype=np.int64)
    rng.shuffle(p)
    return np.concatenate([p, p])


# 12 个二维梯度方向
_GRAD2 = np.array([
    [1, 1], [-1, 1], [1, -1], [-1, -1],
    [1, 0], [-1, 0], [1, 0], [-1, 0],
    [0, 1], [0, -1], [0, 1], [0, -1],
], dtype=np.float64)


def simplex_noise(x, y, seed: int = 0) -> np.ndarray:
    """2D Simplex 噪声（Stefan Gustavson 算法），返回 0..1。

    相比 perlin 方向伪影更少、计算更快。支持标量/同形数组输入。
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    perm = _perm_table(seed)
    F2 = 0.5 * (np.sqrt(3.0) - 1.0)
    G2 = (3.0 - np.sqrt(3.0)) / 6.0
    s = (x + y) * F2
    i = np.floor(x + s).astype(np.int64)
    j = np.floor(y + s).astype(np.int64)
    t = (i + j) * G2
    x0 = x - (i - t)
    y0 = y - (j - t)
    i1 = (x0 > y0).astype(np.int64)
    j1 = 1 - i1

    def _corner(ox, oy, oi, oj):
        cx = x0 - ox
        cy = y0 - oy
        t2 = 0.5 - cx * cx - cy * cy
        t2 = np.where(t2 > 0.0, t2, 0.0)
        gi = (i + oi) & 255
        gj = (j + oj) & 255
        idx = (perm[gi] + perm[gj]) & 255
        g = _GRAD2[idx % 12]
        grad = g[..., 0] * cx + g[..., 1] * cy
        return (t2 * t2) * (t2 * t2) * grad

    z = np.zeros_like(x0, dtype=np.float64)
    n0 = _corner(z, z, 0, 0)
    n1 = _corner(i1 - G2, j1 - G2, i1, j1)
    n2 = _corner(np.full_like(x0, 1.0 - 2.0 * G2),
                 np.full_like(y0, 1.0 - 2.0 * G2), 1, 1)
    n = 70.0 * (n0 + n1 + n2)
    return np.clip((n + 1.0) / 2.0, 0.0, 1.0)


# ---- v2 噪声：域扭曲（domain warp）/ 脊状分形（ridged）/ 细胞（Worley）----
# 说明：以下均为新增 API，不改变上面任何函数的既有语义与输出。


def _hash_ch(ix, iy, seed, channel):
    """同一整数格点的第 channel 路独立随机值（用于特征点抖动）。"""
    return _hash2(ix, iy, np.int64(seed) + np.int64(channel) * 1013)


# 域扭曲可用的基噪声
_WARP_BASES = ("fbm", "fractal", "perlin", "value", "simplex")


def _base_noise(name, x, y, seed):
    """按名字直采基噪声（warp_noise 用）。"""
    name = str(name).lower()
    if name == "fbm":
        return fbm(x, y, seed=seed)
    if name == "fractal":
        return fractal_noise(x, y, seed=seed)
    if name == "perlin":
        return perlin_noise(x, y, seed=seed)
    if name == "value":
        return value_noise(x, y, seed=seed)
    if name == "simplex":
        return simplex_noise(x, y, seed=seed)
    raise ValueError(
        "未知 base=%r，可选：%s" % (name, ", ".join(_WARP_BASES)))


def warp_noise(x, y, seed: int = 0, warp_scale: float = 0.5,
               warp_strength: float = 1.0, base: str = "fbm") -> np.ndarray:
    """域扭曲（domain warp）：先用低频噪声求偏移量，再对扭曲后的坐标采基噪声。

    参数：
        x, y:          标量或同形/可广播数组
        seed:          随机种子
        warp_scale:    扭曲场的采样频率（相对于基噪声，0.5 即低频一半）
        warp_strength: 偏移振幅，单位为输入坐标（1.0 ≈ 一个基噪声格距）
        base:          基噪声，可选 "fbm"（默认，与 fbm() 默认参数一致）、
                       "fractal"、"perlin"、"value"、"simplex"

    偏移量为 ``(2*perlin(...) - 1) * warp_strength``，即每个分量落在
    ±warp_strength 内；因为扭曲场本身是低频平滑的，相邻像素的偏移量近似
    相同，画面会被“拉伸”而不会被撕成噪点。若把 warp_strength 调得远大于 1
    （多个格距）且 warp_scale 不相应调小，位移场梯度会超过 1，画面开始出现
    折叠/噪点——这是域扭曲的固有性质，不是实现问题。

    ``warp_strength=0`` 时偏移量恰为 0，输出与 ``base`` 直采结果逐位相等。

    返回 float64 数组（0..1，随基噪声口径）。
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    xs, ys = np.broadcast_arrays(x, y)
    # 两路不同 seed 的低频扭曲场
    wx = perlin_noise(xs * warp_scale, ys * warp_scale, seed=seed + 1013)
    wy = perlin_noise(xs * warp_scale, ys * warp_scale, seed=seed + 2027)
    # perlin 输出 0..1 -> 居中到 -1..1，再乘强度
    dx = (wx * 2.0 - 1.0) * warp_strength
    dy = (wy * 2.0 - 1.0) * warp_strength
    return _base_noise(base, xs + dx, ys + dy, seed)


def ridged_noise(x, y, octaves: int = 4, lacunarity: float = 2.0,
                 gain: float = 0.5, seed: int = 0,
                 sharpness: float = 2.0) -> np.ndarray:
    """脊状分形（ridged fractal）：每层取脊 + 幂次加深，返回 0..1。

    每层噪声 n∈[0,1] 先折叠成脊 ``r = 1 - |2n - 1|``（n=0.5 处为脊顶），
    再按 ``r ** sharpness`` 加深（sharpness>1 时脊更窄、谷更平）。各层按
    ``gain`` 加权求和后除以权重和（与 fbm 同一归一化口径），故输出 0..1。

    参数：
        octaves:    叠加层数（>=1）
        lacunarity: 每层频率倍增
        gain:       每层振幅衰减
        seed:       随机种子
        sharpness:  脊的幂次（>0，默认 2.0）
    """
    if int(octaves) < 1:
        raise ValueError("octaves 必须 >= 1")
    if not sharpness > 0.0:
        raise ValueError("sharpness 必须 > 0")
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    total = np.zeros(np.broadcast(x, y).shape, dtype=np.float64)
    amp = 1.0
    freq = 1.0
    maxv = 0.0
    for o in range(int(octaves)):
        n = perlin_noise(x * freq, y * freq, seed=seed + o)
        ridge = 1.0 - np.abs(2.0 * n - 1.0)
        total += amp * (ridge ** sharpness)
        maxv += amp
        amp *= gain
        freq *= lacunarity
    return np.clip(total / maxv, 0.0, 1.0)


# 单元格搜索的距离上界：特征点限制在单位格内时，3x3 邻域内最近点距离 <= √2
_CELL_BOUND = np.sqrt(2.0)
_CELL_TYPES = ("f1", "f2", "f2f1")


def cellular_noise(x, y, seed: int = 0, jitter: float = 1.0,
                   return_type: str = "f1") -> np.ndarray:
    """细胞噪声（Worley / Voronoi），返回 0..1。

    每个单位格内放一个特征点，位置为 ``格角 + jitter * hash2(格点)``；
    查询点在其所在格 + 3x3 邻域（共 9 个候选）中搜索。

    参数：
        jitter:      抖动强度，[0,1]。0 = 特征点固定在格角（规整晶格），
                     1 = 特征点可落在格内任意位置（默认）。
        return_type: "f1"   到最近特征点的距离（默认，平滑的细胞块）
                     "f2"   到次近特征点的距离
                     "f2f1" f2 - f1（在细胞边界处趋近 0，可直接当边界线）

    归一化：三种类型都用同一个尺度 ``√2``（3x3 搜索下 F1 的理论上界：
    查询点位于格角、9 个特征点都在各自格的对角远端时取到），再 clip 到
    0..1。用同一尺度是为了让 f1 / f2 / f2f1 三者可直接比较与叠加；
    f2、f2f1 在极少数配置下可能越过 √2，会被 clip（clip 单调，不破坏
    f1<=f2、f2f1>=0 的关系）。
    """
    rt = str(return_type).lower()
    if rt not in _CELL_TYPES:
        raise ValueError(
            "未知 return_type=%r，可选：%s" % (return_type, ", ".join(_CELL_TYPES)))
    if not 0.0 <= jitter <= 1.0:
        raise ValueError("jitter 必须在 [0, 1] 内")
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    xs, ys = np.broadcast_arrays(x, y)
    xi = np.floor(xs).astype(np.int64)
    yi = np.floor(ys).astype(np.int64)
    f1 = np.full(xs.shape, np.inf, dtype=np.float64)
    f2 = np.full(xs.shape, np.inf, dtype=np.float64)
    # 3x3 邻域：对小邻域展开（9 次向量化运算，无逐像素循环）
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            cx = xi + ox
            cy = yi + oy
            px = cx + jitter * _hash_ch(cx, cy, seed, 0)
            py = cy + jitter * _hash_ch(cx, cy, seed, 1)
            ddx = px - xs
            ddy = py - ys
            d = np.sqrt(ddx * ddx + ddy * ddy)
            # 先更新次近，再用旧 f1 更新最近
            f2 = np.minimum(f2, np.maximum(f1, d))
            f1 = np.minimum(f1, d)
    if rt == "f1":
        val = f1
    elif rt == "f2":
        val = f2
    else:
        val = f2 - f1
    return np.clip(val / _CELL_BOUND, 0.0, 1.0)
