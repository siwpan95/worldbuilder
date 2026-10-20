"""道路网：把散落的 POI 连成一张"走得到"的图。

上游 ``poi.place_pois`` 只给点，不给边。本模块补边，并且刻意**不用直线连接**——
直线会穿山、穿湖、贴着悬崖走，看起来像图层贴错了。

做法是网格上的**最小代价路**：

    代价(格) = 1 + slope_cost * 坡度        （缓坡便宜，陡坡贵）
               + river_cost  若为河/湖       （过水要架桥，贵）
               + ∞           若为海          （不修跨海路）

8 邻接、**禁止切角**（对角走必须两个正交邻居都可通行，否则会出现"贴着山尖拐"的路）。
启发函数用欧氏距离（可采纳，A* 结果仍是最优）。

连线策略分两层：

- **主干**：聚落（镇/村/港）之间先取最小生成树（保证连通且总长最短），
  再按欧氏距离补 ``loops`` 条非树边形成回路——纯树状路网在游戏里很难受，
  任何一条边断了就有一片区域到不了。
- **支线**：矿/遗迹/灯塔各自接到**最近的聚落**（单端点），不参与 MST。

过河点不在 ``place_pois`` 里选，而是路修到哪儿、在哪儿下水，就在那儿生成
``bridge`` / ``ford`` 节点（连续水面 ≤2 格记桥，否则记浅滩）。这样过河点
天然落在**路真正要走的位置**，而不是按地形猜。
"""
from __future__ import annotations

import heapq
import itertools
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .poi import (KIND_BRIDGE, KIND_FORD, SETTLEMENT_KINDS, Poi,
                  slope_field)

#: 8 邻接：(dr, dc, 步长)
_DIRS8: Tuple[Tuple[int, int, float], ...] = (
    (0, 1, 1.0), (1, 1, math.sqrt(2)), (1, 0, 1.0), (1, -1, math.sqrt(2)),
    (0, -1, 1.0), (-1, -1, math.sqrt(2)), (-1, 0, 1.0), (-1, 1, math.sqrt(2)),
)


def road_cost_field(world: dict, *, slope_cost: float = 25.0,
                    river_cost: float = 15.0, lake_cost: float = 40.0,
                    sea_blocked: bool = True) -> np.ndarray:
    """建路代价场（float64，海面为 ``inf``）。

    ``slope_cost=25`` 的含义：坡度 0.04（每格降 4%）的格子代价 2.0，
    即"绕行一格平地"与"爬一格 4% 坡"等价。这个比例让路自然走谷地。
    """
    h = np.asarray(world["height"], dtype=np.float64)
    water = np.asarray(world["water"], dtype=np.uint8)
    cost = 1.0 + slope_cost * slope_field(h)
    cost = np.where(water == 1, cost + river_cost, cost)
    cost = np.where(water == 2, cost + lake_cost, cost)
    if sea_blocked:
        cost = np.where(water == 3, np.inf, cost)
    return cost


def _passable(cost: np.ndarray, r: int, c: int) -> bool:
    return 0 <= r < cost.shape[0] and 0 <= c < cost.shape[1] and np.isfinite(cost[r, c])


def _astar(cost: np.ndarray, start: Tuple[int, int],
           goal: Tuple[int, int]) -> Optional[List[Tuple[int, int]]]:
    """在（可能被裁过的）代价场上跑 A*，返回全局/局部格坐标列表。"""
    h, w = cost.shape
    sr, sc = start
    gr, gc = goal
    if not _passable(cost, sr, sc) or not _passable(cost, gr, gc):
        return None

    g = np.full((h, w), np.inf)
    closed = np.zeros((h, w), dtype=bool)
    prev_r = np.full((h, w), -1, dtype=np.int32)
    prev_c = np.full((h, w), -1, dtype=np.int32)
    g[sr, sc] = 0.0
    tie = itertools.count()
    heap = [(math.hypot(gr - sr, gc - sc), next(tie), sr, sc)]

    while heap:
        _f, _t, r, c = heapq.heappop(heap)
        if closed[r, c]:
            continue
        closed[r, c] = True
        if r == gr and c == gc:
            path = [(r, c)]
            pr, pc = prev_r[r, c], prev_c[r, c]
            while pr >= 0:
                path.append((int(pr), int(pc)))
                pr, pc = prev_r[pr, pc], prev_c[pr, pc]
            path.reverse()
            return path

        base = g[r, c]
        for dr, dc, step in _DIRS8:
            nr, nc = r + dr, c + dc
            if not _passable(cost, nr, nc) or closed[nr, nc]:
                continue
            if dr and dc:
                # 禁切角：两个正交邻居任一不可通行就不许斜穿
                if not _passable(cost, r, nc) or not _passable(cost, nr, c):
                    continue
            ng = base + cost[nr, nc] * step
            if ng + 1e-12 < g[nr, nc]:
                g[nr, nc] = ng
                prev_r[nr, nc] = r
                prev_c[nr, nc] = c
                heapq.heappush(heap, (ng + math.hypot(gr - nr, gc - nc),
                                      next(tie), nr, nc))
    return None


def least_cost_path(cost: np.ndarray, start: Tuple[float, float],
                    goal: Tuple[float, float], *,
                    margin: float = 0.35) -> Optional[List[Tuple[int, int]]]:
    """两点间最小代价路（格坐标 ``(r, c)`` 列表，含首尾）。

    先只在两点包围盒外扩 ``margin`` 的子图上找；找不到再退回全图。
    这个裁剪对"跨大陆修路"很有效：全图 A* 要走十几万格，裁剪后通常只有几千格。
    """
    h, w = cost.shape
    sr, sc = int(round(start[0])), int(round(start[1]))
    gr, gc = int(round(goal[0])), int(round(goal[1]))
    if not (0 <= sr < h and 0 <= sc < w and 0 <= gr < h and 0 <= gc < w):
        raise ValueError(f"端点越界：start=({sr},{sc}) goal=({gr},{gc}) shape={cost.shape}")

    span = max(abs(gr - sr), abs(gc - sc))
    pad = int(margin * span) + 4
    r0, r1 = max(0, min(sr, gr) - pad), min(h, max(sr, gr) + pad + 1)
    c0, c1 = max(0, min(sc, gc) - pad), min(w, max(sc, gc) + pad + 1)
    sub = cost[r0:r1, c0:c1]
    path = _astar(sub, (sr - r0, sc - c0), (gr - r0, gc - c0))
    if path is not None:
        return [(r + r0, c + c0) for r, c in path]
    if (r1 - r0, c1 - c0) != (h, w):
        return _astar(cost, (sr, sc), (gr, gc))
    return None


def _simplify(points: Sequence[Tuple[int, int]]) -> List[List[float]]:
    """去掉共线中间点（格坐标是整数，叉积判定是精确的）。"""
    if len(points) <= 2:
        return [[float(c), float(r)] for r, c in points]
    out = [points[0]]
    for i in range(1, len(points) - 1):
        r0, c0 = points[i - 1]
        r1, c1 = points[i]
        r2, c2 = points[i + 1]
        if (r1 - r0) * (c2 - c1) != (c1 - c0) * (r2 - r1):
            out.append(points[i])
    out.append(points[-1])
    return [[float(c), float(r)] for r, c in out]


def _path_length(path: Sequence[Tuple[int, int]]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:]))


def _crossings_on(path: Sequence[Tuple[int, int]], water: np.ndarray) -> List[Tuple[int, int, int]]:
    """找出路径上的连续水面段，返回 ``[(r, c, 段长)]``（取段中点）。"""
    out = []
    i = 0
    n = len(path)
    while i < n:
        r, c = path[i]
        if water[r, c] in (1, 2):
            j = i
            while j + 1 < n and water[path[j + 1][0], path[j + 1][1]] in (1, 2):
                j += 1
            mid = path[(i + j) // 2]
            out.append((mid[0], mid[1], j - i + 1))
            i = j + 1
        else:
            i += 1
    return out


def _mst_edges(pts: Sequence[Tuple[float, float]]) -> List[Tuple[int, int]]:
    """Prim 最小生成树（点数很少，O(n²) 足够）。"""
    n = len(pts)
    if n < 2:
        return []
    in_tree = [False] * n
    in_tree[0] = True
    best = [float("inf")] * n
    near = [0] * n
    for i in range(1, n):
        best[i] = math.hypot(pts[i][0] - pts[0][0], pts[i][1] - pts[0][1])
    out: List[Tuple[int, int]] = []
    for _ in range(n - 1):
        k = min((i for i in range(n) if not in_tree[i]), key=lambda i: best[i])
        in_tree[k] = True
        out.append((near[k], k))
        for i in range(n):
            if not in_tree[i]:
                d = math.hypot(pts[i][0] - pts[k][0], pts[i][1] - pts[k][1])
                if d < best[i]:
                    best[i], near[i] = d, k
    return out


def build_road_network(pois: Sequence[Poi], world: dict, *, seed: int = 0,
                       loops: Optional[int] = None,
                       slope_cost: float = 25.0,
                       river_cost: float = 15.0,
                       lake_cost: float = 40.0,
                       margin: float = 0.35) -> dict:
    """把 POI 连成路网。返回 ``{"nodes", "edges", "crossings", "mask", "stats"}``。

    ``loops`` 缺省取 ``max(1, 聚落数 // 5)``——回路太少则路网脆，太多则像蜘蛛网。
    连不上的点（孤岛、被海隔开）不会中断流程，会记进 ``stats["unreachable"]``。
    """
    h = np.asarray(world["height"])
    water = np.asarray(world["water"], dtype=np.uint8)
    cost = road_cost_field(world, slope_cost=slope_cost,
                           river_cost=river_cost, lake_cost=lake_cost)

    settlements = [p for p in pois if p.kind in SETTLEMENT_KINDS]
    others = [p for p in pois if p.kind not in SETTLEMENT_KINDS]
    loops = max(1, len(settlements) // 5) if loops is None else int(loops)

    edges: List[dict] = []
    unreachable: List[str] = []
    seen_pairs = set()

    def add_edge(a: Poi, b: Poi, kind: str) -> bool:
        key = tuple(sorted((a.id, b.id)))
        if a.id == b.id or key in seen_pairs:
            return False
        seen_pairs.add(key)
        path = least_cost_path(cost, (a.z, a.x), (b.z, b.x), margin=margin)
        if path is None:
            return False
        length = _path_length(path)
        straight = math.hypot(a.z - b.z, a.x - b.x)
        edges.append({
            "a": a.id, "b": b.id, "kind": kind,
            "length": round(length, 3), "straight": round(straight, 3),
            "cost": round(sum(float(cost[r, c]) for r, c in path), 3),
            "points": _simplify(path),
            "_raw": path,
        })
        return True

    # ---- 主干：MST + 回路 ----
    if len(settlements) >= 2:
        pts = [(p.z, p.x) for p in settlements]
        tree = _mst_edges(pts)
        for i, j in tree:
            if not add_edge(settlements[i], settlements[j], "trunk"):
                unreachable.append(f"{settlements[i].id}->{settlements[j].id}")
        tree_keys = {tuple(sorted((settlements[i].id, settlements[j].id))) for i, j in tree}

        candidates = []
        for i in range(len(settlements)):
            for j in range(i + 1, len(settlements)):
                key = tuple(sorted((settlements[i].id, settlements[j].id)))
                if key in tree_keys:
                    continue
                d = math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
                candidates.append((d, i, j))
        candidates.sort()
        for _d, i, j in candidates[:loops]:
            if not add_edge(settlements[i], settlements[j], "loop"):
                unreachable.append(f"{settlements[i].id}->{settlements[j].id}")

    # ---- 支线：非聚落接最近聚落；最近的那个连不上就换下一个 ----
    # （海岛上的遗迹接不到大陆，这是合法结果，记进 unreachable 而不是报错）
    for p in others:
        if not settlements:
            unreachable.append(p.id)
            continue
        ordered = sorted(settlements, key=lambda s: (s.z - p.z) ** 2 + (s.x - p.x) ** 2)
        for s in ordered:
            if add_edge(p, s, "spur"):
                break
        else:
            unreachable.append(p.id)

    # ---- 过河点 ----
    crossings: Dict[Tuple[int, int], dict] = {}
    for e in edges:
        a, b = e["a"], e["b"]
        for r, c, run in _crossings_on(e.pop("_raw"), water):
            if (r, c) in crossings:
                continue
            kind = KIND_BRIDGE if run <= 2 else KIND_FORD
            cid = f"{kind}-{sum(1 for x in crossings.values() if x['kind'] == kind):02d}"
            crossings[(r, c)] = Poi(
                id=cid, kind=kind, x=float(c), z=float(r),
                name=f"{'桥' if kind == KIND_BRIDGE else '浅滩'} {a}·{b}",
                meta={"water_run": int(run), "edge": [a, b]},
            ).to_dict()

    mask = np.zeros(h.shape, dtype=bool)
    for e in edges:
        for x, z in e["points"]:
            mask[int(round(z)), int(round(x))] = True

    total_len = sum(e["length"] for e in edges)
    total_straight = sum(e["straight"] for e in edges)
    stats = {
        "nodes": len(pois) + len(crossings),
        "settlements": len(settlements),
        "edges": len(edges),
        "crossings": len(crossings),
        "length": round(total_len, 3),
        "detour": round(total_len / total_straight, 3) if total_straight else 0.0,
        "unreachable": unreachable,
    }
    return {
        "nodes": [p.to_dict() for p in pois] + list(crossings.values()),
        "edges": edges,
        "crossings": list(crossings.values()),
        "mask": mask,
        "stats": stats,
    }


def describe_network(net: dict) -> str:
    """一行式摘要。"""
    s = net.get("stats", {})
    return (f"路网：{s.get('settlements', 0)} 聚落 / {s.get('edges', 0)} 条路 / "
            f"{s.get('crossings', 0)} 处过河 / 总长 {s.get('length', 0):.0f} 格 / "
            f"绕行比 {s.get('detour', 0):.2f}"
            + (f" / 未连通 {len(s.get('unreachable', []))}" if s.get("unreachable") else ""))
