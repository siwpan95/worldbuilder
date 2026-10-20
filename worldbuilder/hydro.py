"""水文：填洼 → 流向 → 流量累积 → 河流 / 湖泊 / 海岸线。

这是「高度图 → 有地理逻辑的世界」缺的那一段。此前 ``terrain.py`` 只做到
「高度 + 湿度阈值 → 生物群系」，水系是空的；而水系又是气候（雨影）与聚落
（沿河而居）的前置。

顺序不可颠倒：
    1. ``fill_depressions`` —— 先消掉内流洼地，否则下游累积会在坑里断掉；
    2. ``flow_directions``  —— D8 最陡下降（填洼时加的 ε 让平地面也有微坡）；
    3. ``flow_accumulation``—— 按高程降序把本格汇水面积加到下游；
    4. ``extract_rivers``   —— 从河源顺流而下切成折线；
    5. ``lakes`` / ``coastline`` —— 顺带产出湖面与海岸。

算法出处（实现自写，未取代码）：
    - 填洼：Barnes, Lehman & Mulla (2014) *Priority-Flood*；
    - 流向：O'Callaghan & Mark (1984) D8；
    - 河宽：水力几何关系的常用幂律 ``w ∝ Q^0.5``。
层的划分参考 Azgaar Fantasy Map Generator（MIT）的世界生成流水线，
但本模块只有算法与接口，没有移植其实现。
"""
from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

#: 8 邻域：(dy, dx, 距离)。索引即 D8 方向码。
NEIGHBORS: Tuple[Tuple[int, int, float], ...] = (
    (0, 1, 1.0),                       # 0 E
    (-1, 1, 1.4142135623730951),       # 1 NE
    (-1, 0, 1.0),                      # 2 N
    (-1, -1, 1.4142135623730951),      # 3 NW
    (0, -1, 1.0),                      # 4 W
    (1, -1, 1.4142135623730951),       # 5 SW
    (1, 0, 1.0),                       # 6 S
    (1, 1, 1.4142135623730951),        # 7 SE
)

#: 四邻域，用于湖泊连通块与海岸判定
_NEIGHBORS4 = ((0, 1), (-1, 0), (0, -1), (1, 0))


def fill_depressions(height: np.ndarray, epsilon: float = 1e-5,
                     max_cells: int = 4_000_000) -> np.ndarray:
    """Priority-Flood 填洼：把每个封闭洼地抬到其出水口高程 + ε。

    返回与输入同形的新数组（float64）。边界视为出水口，因此**边界高度不变**，
    内部洼地被填平并带一点朝出水口的坡度——这一点坡度很关键：D8 是"严格下降"
    才给方向，完全平的地面会退化成一片无方向的死区。

    参数：
        epsilon:   每格抬升量。太小会被 float32 精度吃掉，默认 1e-5 是按
                   "高度图归一化到 0..1" 的量级选的。
        max_cells: 规模保护。Priority-Flood 是 Python 堆实现的 O(n log n)，
                   400 万格以上建议改用分块或 numba 版本（本库保持零额外依赖）。
    """
    h = np.asarray(height, dtype=np.float64)
    if h.ndim != 2:
        raise ValueError(f"height 必须是二维数组，收到 shape={h.shape}")
    rows, cols = h.shape
    if rows < 3 or cols < 3:
        raise ValueError(f"高度图至少 3x3，收到 {rows}x{cols}")
    if h.size > max_cells:
        raise ValueError(
            f"高度图 {rows}x{cols}={h.size} 格超过上限 {max_cells}；"
            f"请分块生成或调大 max_cells"
        )

    filled = h.copy()
    closed = np.zeros(h.shape, dtype=bool)
    heap: List[Tuple[float, int]] = []

    # 边界全部入堆（它们就是出水口）
    for c in range(cols):
        for r in (0, rows - 1):
            i = r * cols + c
            if not closed.flat[i]:
                closed.flat[i] = True
                heap.append((filled.flat[i], i))
    for r in range(rows):
        for c in (0, cols - 1):
            i = r * cols + c
            if not closed.flat[i]:
                closed.flat[i] = True
                heap.append((filled.flat[i], i))
    heapq.heapify(heap)

    flat_filled = filled.reshape(-1)
    flat_h = h.reshape(-1)
    dirs = [(dy * cols + dx) for dy, dx, _ in NEIGHBORS]

    while heap:
        level, i = heapq.heappop(heap)
        r, c = divmod(i, cols)
        for (dy, dx, _), off in zip(NEIGHBORS, dirs):
            nr, nc = r + dy, c + dx
            if nr < 0 or nr >= rows or nc < 0 or nc >= cols:
                continue
            j = i + off
            if closed.flat[j]:
                continue
            closed.flat[j] = True
            cand = level + epsilon if level + epsilon > flat_h[j] else flat_h[j]
            flat_filled[j] = cand
            heapq.heappush(heap, (cand, j))

    return filled


def flow_directions(height: np.ndarray) -> np.ndarray:
    """D8 最陡下降方向码（0..7，见 ``NEIGHBORS``）；无下游（洼地/边界）为 -1。

    只在**有严格更低邻居**时给方向。把 ``fill_depressions`` 的输出喂进来，
    平地面会因为 ε 坡度而自然获得方向。
    """
    h = np.asarray(height, dtype=np.float64)
    rows, cols = h.shape
    best = np.zeros_like(h)
    dirs = np.full(h.shape, -1, dtype=np.int8)

    for k, (dy, dx, dist) in enumerate(NEIGHBORS):
        nb = np.full_like(h, np.inf)
        # 有效重叠区：源 (r+dy, c+dx) -> 目标 (r, c)
        src_r = slice(max(0, dy), rows + min(0, dy))
        dst_r = slice(max(0, -dy), rows + min(0, -dy))
        src_c = slice(max(0, dx), cols + min(0, dx))
        dst_c = slice(max(0, -dx), cols + min(0, -dx))
        nb[dst_r, dst_c] = h[src_r, src_c]
        slope = (h - nb) / dist
        upd = slope > best
        best[upd] = slope[upd]
        dirs[upd] = k

    dirs[best <= 0.0] = -1
    return dirs


def flow_accumulation(height: np.ndarray, dirs: Optional[np.ndarray] = None,
                      weights: Optional[np.ndarray] = None) -> np.ndarray:
    """汇水累积：每格初始为其自身（或 ``weights``），按高程**降序**加到下游。

    返回 shape 同高度的 float64 数组，单位是"格数"（或权重之和）。
    复杂度 O(n log n)（排序）+ O(n)（累加），n = 格数。
    """
    h = np.asarray(height, dtype=np.float64)
    rows, cols = h.shape
    if dirs is None:
        dirs = flow_directions(h)
    d = np.asarray(dirs, dtype=np.int8).reshape(-1)
    acc = (np.ones(h.size, dtype=np.float64) if weights is None
           else np.asarray(weights, dtype=np.float64).reshape(-1).copy())

    order = np.argsort(-h.reshape(-1), kind="stable")
    offsets = [dy * cols + dx for dy, dx, _ in NEIGHBORS]
    for i in order:
        k = d[i]
        if k >= 0:
            j = i + offsets[k]
            if 0 <= j < acc.size:
                acc[j] += acc[i]
    return acc.reshape(h.shape)


def river_width(acc: np.ndarray, w0: float = 1.0, exponent: float = 0.5) -> np.ndarray:
    """河宽幂律 ``w = w0 * acc^exponent``（水力几何的常用近似）。"""
    return (w0 * np.power(np.maximum(np.asarray(acc, dtype=np.float64), 1.0),
                          exponent)).astype(np.float32)


def extract_rivers(height: np.ndarray, acc: np.ndarray, dirs: np.ndarray,
                   threshold: float = 40.0, min_points: int = 4) -> List[dict]:
    """抽出河流折线。

    做法：把 ``acc >= threshold`` 且**没有同为河流的上游**的格子当河源，
    顺流而下直到（a）无下游、（b）撞上已被别的河走过的格子（汇流）。
    每条河返回 ``{points, mouth, acc_max, length, width_max}``，
    ``points`` 是 ``[(x, y), ...]``，x=列、y=行（像素中心）。

    ``threshold`` 决定"多小的水算溪"：网格越大应越大（经验值 ≈ 网格边长的 1/4）。
    """
    h = np.asarray(height, dtype=np.float64)
    a = np.asarray(acc, dtype=np.float64).reshape(-1)
    d = np.asarray(dirs, dtype=np.int8).reshape(-1)
    rows, cols = h.shape
    offsets = [dy * cols + dx for dy, dx, _ in NEIGHBORS]

    is_river = (a >= threshold) & (d >= 0)
    # 上游计数：有上游河格流入的，不算河源
    has_river_upstream = np.zeros(h.size, dtype=bool)
    for i in np.nonzero(is_river)[0]:
        k = int(d[i])
        if k >= 0:
            j = int(i) + offsets[k]
            if 0 <= j < h.size:
                has_river_upstream[j] = True

    sources = np.nonzero(is_river & ~has_river_upstream)[0]
    # 从汇水量大的河源先走，保证干流优先占位（支流会在汇合处停下）
    sources = sources[np.argsort(-a[sources], kind="stable")]

    visited = np.zeros(h.size, dtype=bool)
    rivers: List[dict] = []
    for s in sources:
        pts: List[Tuple[float, float]] = []
        i = int(s)
        while True:
            visited[i] = True
            r, c = divmod(i, cols)
            pts.append((float(c), float(r)))
            k = int(d[i])
            if k < 0:
                break
            j = i + offsets[k]
            if not (0 <= j < h.size) or visited[j]:
                break
            if not is_river[j] and len(pts) >= min_points:
                # 汇入非河流段（湖/海/边界），再走一格收尾
                r2, c2 = divmod(j, cols)
                pts.append((float(c2), float(r2)))
                break
            i = j
        if len(pts) < min_points:
            continue
        idx = [int(r) * cols + int(c) for c, r in pts]
        rivers.append({
            "points": pts,
            "mouth": pts[-1],
            "acc_max": float(a[idx].max()),
            "length": float(len(pts) - 1),
            "width_max": float(river_width(np.array([a[idx].max()]))[0]),
        })
    rivers.sort(key=lambda r: -r["acc_max"])
    return rivers


def lakes(height: np.ndarray, filled: np.ndarray,
          epsilon: float = 1e-5, min_area: int = 4) -> dict:
    """填洼产生的湖：``filled - height > epsilon/2`` 的连通块。

    返回 ``{"mask", "count", "lakes": [{area, bbox, surface, cells}]}``。
    ``cells`` 是扁平索引数组，方便后续按湖取属性（水位/入流/出流）。
    """
    h = np.asarray(height, dtype=np.float64)
    f = np.asarray(filled, dtype=np.float64)
    mask = (f - h) > epsilon * 0.5
    rows, cols = h.shape
    labels = np.zeros(h.shape, dtype=np.int32)
    out: List[dict] = []
    cur = 0
    for start in np.nonzero(mask.reshape(-1))[0]:
        if labels.reshape(-1)[start]:
            continue
        cur += 1
        stack = [int(start)]
        labels.reshape(-1)[start] = cur
        cells: List[int] = []
        while stack:
            i = stack.pop()
            cells.append(i)
            r, c = divmod(i, cols)
            for dy, dx in _NEIGHBORS4:
                nr, nc = r + dy, c + dx
                if 0 <= nr < rows and 0 <= nc < cols:
                    j = nr * cols + nc
                    if mask.reshape(-1)[j] and not labels.reshape(-1)[j]:
                        labels.reshape(-1)[j] = cur
                        stack.append(j)
        if len(cells) < min_area:
            continue
        arr = np.array(cells, dtype=np.int64)
        rs, cs = arr // cols, arr % cols
        out.append({
            "area": int(len(cells)),
            "bbox": (int(rs.min()), int(cs.min()), int(rs.max()), int(cs.max())),
            "surface": float(f.reshape(-1)[arr].max()),
            "cells": arr,
        })
    out.sort(key=lambda x: -x["area"])
    return {"mask": mask, "count": len(out), "lakes": out}


def coastline(height: np.ndarray, sea_level: float = 0.0) -> np.ndarray:
    """海岸线掩码：陆地格中，四邻域里有水（``<= sea_level``）的那些。"""
    h = np.asarray(height, dtype=np.float64)
    land = h > sea_level
    water = ~land
    rows, cols = h.shape
    near = np.zeros_like(land)
    for dy, dx in _NEIGHBORS4:
        src_r = slice(max(0, dy), rows + min(0, dy))
        dst_r = slice(max(0, -dy), rows + min(0, -dy))
        src_c = slice(max(0, dx), cols + min(0, dx))
        dst_c = slice(max(0, -dx), cols + min(0, -dx))
        near[dst_r, dst_c] |= water[src_r, src_c]
    return land & near


def hydrology(height: np.ndarray, sea_level: float = 0.0,
              epsilon: float = 1e-5, river_threshold: Optional[float] = None,
              with_rivers: bool = True) -> dict:
    """一步跑完水文链，返回全部中间产物。

    返回 dict：
        ``filled`` 填洼后的高度 / ``dirs`` D8 方向 / ``acc`` 汇水累积 /
        ``rivers`` 折线列表 / ``lakes`` 湖泊信息 / ``coast`` 海岸掩码 /
        ``river_mask`` 汇水超过阈值的格 / ``width`` 河宽场
    ``river_threshold`` 缺省取 ``max(12, 格数/80)`` —— 这个分母是按"河数不随分辨率漂移"
    实测调的：96²/192²/256² 在同一 seed 下都落在 18~22 条主干河（见 tests/test_hydro.py）。
    """
    h = np.asarray(height, dtype=np.float64)
    filled = fill_depressions(h, epsilon=epsilon)
    dirs = flow_directions(filled)
    acc = flow_accumulation(filled, dirs)
    thr = (float(river_threshold) if river_threshold is not None
           else max(12.0, h.size / 80.0))
    river_mask = (acc >= thr) & (dirs >= 0)
    out = {
        "filled": filled.astype(np.float32),
        "dirs": dirs,
        "acc": acc.astype(np.float32),
        "lakes": lakes(h, filled, epsilon=epsilon),
        "coast": coastline(h, sea_level=sea_level),
        "river_mask": river_mask,
        "width": river_width(acc),
        "river_threshold": thr,
    }
    out["rivers"] = (extract_rivers(filled, acc, dirs, threshold=thr)
                     if with_rivers else [])
    return out
