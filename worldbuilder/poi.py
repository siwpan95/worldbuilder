"""兴趣点（POI）选址：把"地形上合理的位置"变成"玩法上值得去的地方"。

上游 ``worldgen.generate_world_full`` 只回答"这里是什么地形"，不回答"人会住在哪"。
本模块补这一段：按**可达水源、坡度、海拔带、群系、彼此间距**给每个格子打分，
再用带抑制半径的贪心挑选（不是纯随机撒点——随机撒点会出"沙漠正中的渔港"）。

选址规则（都可调，默认值按 256² 世界标定）：

===========  ==================================================  ==============
类型          条件                                                 主要依据
===========  ==================================================  ==============
``town``      陆地、缓坡、近淡水/海岸、非荒漠苔原                     水源 + 平坦 + 群系
``village``   同上，间距更小、可以更靠近别的村镇                      同上
``port``      陆地且**紧邻海**，河口加分                             海岸 + 淡水
``mine``      陆地、坡度上四分位、海拔高于海面 15%                    坡度 + 海拔
``ruin``      陆地、远离聚落（距离越远分越高）                        孤立度
``lighthouse`` 陆地且紧邻海、远离聚落                              海岸 + 孤立度
===========  ==================================================  ==============

被水覆盖的格子**永远不选**（``water != 0`` 直接排除）。

名字复用 ``namegen.NameGenerator``；同一世界内去重（重名加序号后缀）。
ID 形如 ``town-03``，跨仓唯一且稳定——``worldspec`` 与 an-engine 的 ``MapGraph``
都靠它做节点标识。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import climate as C
from .namegen import NameGenerator

#: 聚落类（会作为路网主干节点）
KIND_TOWN = "town"
KIND_VILLAGE = "village"
KIND_PORT = "port"
#: 非聚落类（作为支线端点）
KIND_MINE = "mine"
KIND_RUIN = "ruin"
KIND_LIGHTHOUSE = "lighthouse"
#: 由路网自动生成的过河点（不在 place_pois 里选）
KIND_BRIDGE = "bridge"
KIND_FORD = "ford"

SETTLEMENT_KINDS: Tuple[str, ...] = (KIND_TOWN, KIND_PORT, KIND_VILLAGE)

#: 群系 -> 建聚落适宜度（0..1）。水域与高山几乎不可能，荒漠/苔原只适合少量。
_BIOME_SETTLE_LUT = np.zeros(12, dtype=np.float64)
_BIOME_SETTLE_LUT[C.BEACH] = 0.25
_BIOME_SETTLE_LUT[C.TROPICAL_RAINFOREST] = 0.75
_BIOME_SETTLE_LUT[C.SAVANNA] = 0.80
_BIOME_SETTLE_LUT[C.HOT_DESERT] = 0.12
_BIOME_SETTLE_LUT[C.TEMPERATE_FOREST] = 1.00
_BIOME_SETTLE_LUT[C.TEMPERATE_RAINFOREST] = 0.85
_BIOME_SETTLE_LUT[C.GRASSLAND] = 1.00
_BIOME_SETTLE_LUT[C.COLD_DESERT] = 0.30
_BIOME_SETTLE_LUT[C.TAIGA] = 0.60
_BIOME_SETTLE_LUT[C.TUNDRA] = 0.35
_BIOME_SETTLE_LUT[C.ALPINE] = 0.05


@dataclass
class Poi:
    """一个兴趣点。

    ``x`` 是列坐标、``z`` 是行坐标（与 ``worldspec`` 的 ``height[r][c]`` 同约定：
    r ↔ z、c ↔ x），单位是格。下游要换成米就乘 ``meta["tile_m"]``。
    """

    id: str
    kind: str
    x: float
    z: float
    name: str = ""
    score: float = 0.0
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "x": float(self.x),
                "z": float(self.z), "name": self.name,
                "score": float(self.score), "meta": dict(self.meta)}

    @classmethod
    def from_dict(cls, data: dict) -> "Poi":
        return cls(id=str(data["id"]), kind=str(data["kind"]),
                   x=float(data["x"]), z=float(data["z"]),
                   name=str(data.get("name", "")),
                   score=float(data.get("score", 0.0)),
                   meta=dict(data.get("meta") or {}))

    def __repr__(self) -> str:
        return f"Poi({self.id}, {self.kind}, x={self.x:.1f}, z={self.z:.1f})"


# ─── 地形派生量 ──────────────────────────────────────────

def slope_field(height: np.ndarray) -> np.ndarray:
    """坡度场（中心差分梯度模长，单位是"每格高度差"）。

    高度图归一化到 0..1 时，典型值在 0.002~0.08 之间；直接乘 ``tile_m``
    就得到真实坡度（米/米）。
    """
    h = np.asarray(height, dtype=np.float64)
    gy, gx = np.gradient(h)
    return np.hypot(gx, gy)


def main_landmass(water: np.ndarray, *, passable_rivers: bool = True) -> np.ndarray:
    """返回**面积最大的连片可通行陆地**掩码。

    为什么需要它：``place_pois`` 的"遗迹越孤立越好"会把点推到离岸小岛上，
    路网随后接不过去（这不是 bug，是评分目标与可达性目标冲突）。
    先把候选限制在主陆块内，遗迹就只能落在"人迹罕至但仍走得到"的地方。

    连通性判据里**河是可通行的**（``water == 1``）——否则一条贯穿全岛的河
    会把陆块劈成两半，主陆块只剩一半。湖泊（2）与海（3）不可通行。
    """
    w = np.asarray(water, dtype=np.uint8)
    walk = (w == 0) | (w == 1) if passable_rivers else (w == 0)
    h, wd = walk.shape
    labels = np.full((h, wd), -1, dtype=np.int32)
    sizes: Dict[int, int] = {}
    label = 0
    for r0 in range(h):
        for c0 in range(wd):
            if not walk[r0, c0] or labels[r0, c0] >= 0:
                continue
            stack = [(r0, c0)]
            labels[r0, c0] = label
            size = 0
            while stack:
                r, c = stack.pop()
                size += 1
                for dr, dc in ((0, 1), (-1, 0), (0, -1), (1, 0)):
                    nr, nc = r + dr, c + dc
                    if (0 <= nr < h and 0 <= nc < wd and walk[nr, nc]
                            and labels[nr, nc] < 0):
                        labels[nr, nc] = label
                        stack.append((nr, nc))
            sizes[label] = size
            label += 1
    if not sizes:
        return np.zeros((h, wd), dtype=bool)
    best = max(sizes, key=lambda k: sizes[k])
    return (labels == best) & np.asarray(water == 0)


def _dilate(mask: np.ndarray, steps: int = 1) -> np.ndarray:
    """4 邻域膨胀（边界按 False 处理，不做环绕）。"""
    out = np.asarray(mask, dtype=bool)
    for _ in range(max(0, int(steps))):
        p = np.pad(out, 1, constant_values=False)
        out = (p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1]
               | p[1:-1, :-2] | p[1:-1, 2:])
    return out


def _dist_to_points(shape: Tuple[int, int], pts: Sequence[Tuple[float, float]]) -> np.ndarray:
    """到最近给定点的欧氏距离场（点数很少，直接暴力比距离变换更省事）。"""
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    d = np.full(shape, np.inf, dtype=np.float64)
    for r, c in pts:
        d = np.minimum(d, np.hypot(yy - r, xx - c))
    return d


def _pick_sites(score: np.ndarray, allowed: np.ndarray, count: int,
                spacing: int, occupied: np.ndarray) -> List[Tuple[int, int, float]]:
    """按分数从高到低取点，每取一个就把半径 ``spacing`` 的圆盘压成 -inf。"""
    if count <= 0:
        return []
    sc = np.where(allowed & ~occupied, score, -np.inf).astype(np.float64)
    h, w = sc.shape
    picked: List[Tuple[int, int, float]] = []
    for _ in range(int(count)):
        i = int(np.argmax(sc))
        if not np.isfinite(sc.flat[i]):
            break
        r, c = divmod(i, w)
        picked.append((r, c, float(score[r, c])))
        r0, r1 = max(0, r - spacing), min(h, r + spacing + 1)
        c0, c1 = max(0, c - spacing), min(w, c + spacing + 1)
        yy, xx = np.ogrid[r0:r1, c0:c1]
        disk = (yy - r) ** 2 + (xx - c) ** 2 <= spacing * spacing
        sc[r0:r1, c0:c1][disk] = -np.inf
        occupied[r0:r1, c0:c1] |= disk
    return picked


def _auto_counts(cells: int) -> Dict[str, int]:
    """按世界格数估一个"不空旷也不拥挤"的数量。256² 得到 11 个聚落。"""
    settlements = int(max(4, min(28, round(cells / 4500.0))))
    return {
        "settlements": settlements,
        "ports": max(1, settlements // 4),
        "mines": max(1, settlements // 3),
        "ruins": max(1, settlements // 4),
        "lighthouses": max(0, settlements // 6),
    }


def place_pois(world: dict, *, seed: int = 0,
               settlements: Optional[int] = None,
               ports: Optional[int] = None,
               mines: Optional[int] = None,
               ruins: Optional[int] = None,
               lighthouses: Optional[int] = None,
               spacing: Optional[int] = None,
               max_slope: Optional[float] = None) -> List[Poi]:
    """给一个 ``generate_world_full`` 的世界选兴趣点，返回按分数降序的列表。

    参数：
        settlements: 村镇总数（含港口）。``None`` 按格数自动（``格数/6000``，4..28）。
        spacing:     任意两个 POI 的最小间距（格）。``None`` 取 ``min(边长)*0.10``。
        max_slope:   聚落可接受的最大坡度。``None`` 取陆坡度的 35 分位——
                     这个取法比写死阈值稳：不同 ``scale`` 生成的地形起伏差异很大。

    返回的列表里 ``id`` 形如 ``town-00``、``port-00``，同一世界内唯一。
    """
    h = np.asarray(world["height"], dtype=np.float64)
    water = np.asarray(world["water"], dtype=np.uint8)
    biome = np.asarray(world.get("biomes") if world.get("biomes") is not None
                       else np.zeros(h.shape, dtype=np.uint8))
    sea = float(world.get("sea_level", 0.0))
    if h.ndim != 2:
        raise ValueError(f"height 必须是二维，收到 shape={h.shape}")

    land = water == 0
    if not land.any():
        return []
    main = main_landmass(water)          # 主陆块：所有 POI 都落在同一块上，路才连得通
    if not main.any():
        return []
    slope = slope_field(h)
    land_slope = slope[land]
    if max_slope is None:
        max_slope = float(np.clip(np.percentile(land_slope, 35), 0.004, 0.08))
    spacing = int(spacing) if spacing is not None else max(3, int(0.10 * min(h.shape)))

    auto = _auto_counts(int(h.size))
    n_settle = auto["settlements"] if settlements is None else int(settlements)
    n_port = auto["ports"] if ports is None else int(ports)
    n_mine = auto["mines"] if mines is None else int(mines)
    n_ruin = auto["ruins"] if ruins is None else int(ruins)
    n_light = auto["lighthouses"] if lighthouses is None else int(lighthouses)
    n_village = max(0, n_settle - n_port)

    fresh = (water == 1) | (water == 2)
    sea_m = water == 3
    coast = land & _dilate(sea_m, 1)

    # 水源/海岸分段衰减：紧邻最值钱，8 格以外基本不加分
    fresh_band = (1.00 * _dilate(fresh, 1) + 0.55 * _dilate(fresh, 3)
                  + 0.25 * _dilate(fresh, 8)).astype(np.float64)
    sea_band = (0.70 * _dilate(sea_m, 1) + 0.35 * _dilate(sea_m, 4)).astype(np.float64)
    flat = 1.0 / (1.0 + 60.0 * slope)
    biome_fit = _BIOME_SETTLE_LUT[np.clip(biome.astype(np.int64), 0, 11)]
    # 低地偏好：海面以上 2%~22% 高度最合适，再高就衰减
    above = np.clip(h - sea, 0.0, None)
    lowland = np.clip(1.0 - np.abs(above - 0.10) / 0.20, 0.0, 1.0)

    rng = np.random.RandomState(seed)
    jitter = rng.random(h.shape) * 1e-3          # 只用来打散平局，不影响排序语义
    occupied = np.zeros(h.shape, dtype=bool)
    pois: List[Poi] = []

    def emit(kind: str, r: int, c: int, score: float) -> None:
        pois.append(Poi(
            id=f"{kind}-{sum(1 for p in pois if p.kind == kind):02d}",
            kind=kind, x=float(c), z=float(r),
            score=float(score),
            meta={"elevation": float(h[r, c]),
                  "biome": int(biome[r, c]),
                  "slope": float(slope[r, c])},
        ))

    # ---- 聚落（镇 / 村） ----
    settle_score = (2.20 * fresh_band + 1.00 * sea_band + 2.00 * flat
                    + 1.20 * biome_fit + 0.80 * lowland + jitter)
    settle_ok = main & (slope <= max_slope)
    for r, c, s in _pick_sites(settle_score, settle_ok, n_village, spacing, occupied):
        emit(KIND_VILLAGE if len(pois) >= max(1, n_village // 3) else KIND_TOWN, r, c, s)
    # 前 1/3 记为镇（更中心、更值钱），其余为村

    # ---- 港口：必须紧邻海 ----
    port_score = (2.00 * _dilate(sea_m, 1) + 1.40 * fresh_band
                  + 1.50 * flat + 0.60 * biome_fit + jitter)
    for r, c, s in _pick_sites(port_score, coast & main, n_port, spacing, occupied):
        emit(KIND_PORT, r, c, s)

    # ---- 矿：陡坡 + 高处 ----
    slope_norm = slope / (float(slope.max()) + 1e-12)
    high_biome = np.isin(biome, (C.ALPINE, C.TAIGA, C.COLD_DESERT)).astype(np.float64)
    mine_score = (2.20 * slope_norm + 1.20 * high_biome
                  + 0.80 * np.clip(above / 0.4, 0.0, 1.0) + 0.40 * fresh_band + jitter)
    mine_ok = (main & (slope >= float(np.percentile(land_slope, 75)))
               & (above > 0.15))
    for r, c, s in _pick_sites(mine_score, mine_ok, n_mine, max(2, spacing // 2), occupied):
        emit(KIND_MINE, r, c, s)

    # ---- 遗迹：越孤立越值钱 ----
    settle_pts = [(p.z, p.x) for p in pois if p.kind in SETTLEMENT_KINDS]
    dist_settle = _dist_to_points(h.shape, settle_pts) if settle_pts else np.zeros(h.shape)
    dmax = float(dist_settle[np.isfinite(dist_settle)].max()) or 1.0
    ruin_score = (1.80 * dist_settle / dmax + 0.60 * biome_fit
                  + 0.40 * (1.0 - flat) + jitter)
    ruin_ok = main & (slope <= float(np.percentile(land_slope, 60)))
    for r, c, s in _pick_sites(ruin_score, ruin_ok, n_ruin, max(2, spacing // 2), occupied):
        emit(KIND_RUIN, r, c, s)

    # ---- 灯塔：海岸 + 远离聚落 ----
    light_score = (1.50 * _dilate(sea_m, 1) + 1.50 * dist_settle / dmax
                   + 0.40 * flat + jitter)
    for r, c, s in _pick_sites(light_score, coast & main, n_light, spacing, occupied):
        emit(KIND_LIGHTHOUSE, r, c, s)

    _assign_names(pois, seed)
    pois.sort(key=lambda p: (-p.score, p.id))
    return pois


def _assign_names(pois: List[Poi], seed: int) -> None:
    """就地填名字；同世界内去重（重名加 ``II/III`` 后缀）。"""
    ng = NameGenerator(style="fantasy", seed=seed)
    used: Dict[str, int] = {}
    for p in pois:
        base = ng.generate(1)[0]
        n = used.get(base, 0)
        used[base] = n + 1
        p.name = base if n == 0 else f"{base} {('II', 'III', 'IV', 'V')[min(n - 1, 3)]}"


def describe(pois: Sequence[Poi], world: Optional[dict] = None) -> str:
    """一行式摘要（CLI / 日志用）。"""
    counts: Dict[str, int] = {}
    for p in pois:
        counts[p.kind] = counts.get(p.kind, 0) + 1
    parts = [f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    head = f"兴趣点 {len(pois)} 个：" + ("、".join(parts) if parts else "无")
    if world is not None and pois:
        sea = float(world.get("sea_level", 0.0))
        land = np.asarray(world["water"]) == 0
        elev = np.array([p.meta.get("elevation", 0.0) for p in pois])
        head += (f"；海拔 {elev.min():.3f}~{elev.max():.3f}（海面 {sea:.3f}）"
                 f"；陆地占比 {land.mean():.0%}")
    return head
