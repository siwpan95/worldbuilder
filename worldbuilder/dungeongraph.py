"""地牢的图表示：房间 = 节点，走廊 = 边，再叠加**锁钥**与语义标注。

``dungeon.py`` 产出的是**网格**（能画、能寻路），但关卡设计要的是**图**：
哪间房是入口、哪条路要先找钥匙、Boss 在最深处、宝箱在支线尽头。
两套表示各有用途，本模块负责从网格抽出图，并保证抽出来的图**可解**。

抽图分三步：

1. **认房间**：给了 BSP 的 ``rooms`` 就直接用矩形；否则用「3×3 全地板」的核心格
   做 4 连通分量，再把核心向外扩一圈（WFC 生成的十字形房间核心只有一格，也能认出来）。
2. **连边**：从每个房间的多源 BFS 穿过走廊格，第一次碰到别的房间就记一条边，
   路径原样保留（折线，坐标是格）。不穿过第三方房间，所以不会出现"借道别人家"。
3. **加语义**：入口取贴边房间；Boss 取图上离入口最远的房间；锁钥按**从入口出发的
   生成树**挑深层边，钥匙放在**不经过任何锁就能到达**的房间——这条是"可解"的定义，
   也是测试里钉住的不变量。

输出结构与 ``worldspec`` 的 ``graph.json`` 同形（``nodes`` + ``edges``，边带 ``points``），
所以下游 ``MapGraph`` 那套消费逻辑可以直接吃，不必为地牢再写一份。
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

#: 房间语义
KIND_ENTRANCE = "entrance"
KIND_ROOM = "room"
KIND_BOSS = "boss"
KIND_TREASURE = "treasure"
KIND_GUARD = "guard"

#: 边语义
EDGE_OPEN = "open"
EDGE_LOCKED = "locked"
EDGE_LOOP = "loop"

_NEIGHBORS4 = ((0, 1), (-1, 0), (0, -1), (1, 0))


@dataclass
class Room:
    """一间房（半开矩形 + 实际占用的地板格）。"""

    idx: int
    x0: int
    z0: int
    x1: int
    z1: int
    cells: List[Tuple[int, int]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    @property
    def center(self) -> Tuple[float, float]:
        """房间中心 ``(x, z)``（格坐标，浮点）。"""
        return ((self.x0 + self.x1 - 1) / 2.0, (self.z0 + self.z1 - 1) / 2.0)

    @property
    def area(self) -> int:
        return len(self.cells) or max(0, (self.x1 - self.x0) * (self.z1 - self.z0))

    def id(self) -> str:
        return f"room-{self.idx:02d}"


def _as_grid(grid) -> np.ndarray:
    g = np.asarray(grid)
    if g.ndim != 2:
        raise ValueError(f"grid 必须是二维，收到 shape={g.shape}")
    return g.astype(bool, copy=False)


def detect_rooms(grid, *, min_core: int = 1) -> List[Room]:
    """从 1/0 网格自动认房间（3×3 核心 + 向外扩一圈）。"""
    g = _as_grid(grid)
    h, w = g.shape
    core = np.zeros((h, w), dtype=bool)
    if h >= 3 and w >= 3:
        m = g[1:-1, 1:-1].copy()
        hh, ww = m.shape
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                m &= g[1 + dr:1 + dr + hh, 1 + dc:1 + dc + ww]
        core[1:-1, 1:-1] = m

    if not core.any():
        # 薄墙地牢（WFC 的十字房间、1 格宽走廊）没有任何 3x3 空块，
        # 退化成「交叉口」核心：地板格且四邻中至少 3 个是地板。
        deg = np.zeros((h, w), dtype=np.int8)
        for dr, dc in _NEIGHBORS4:
            deg[max(0, dr):h + min(0, dr), max(0, dc):w + min(0, dc)] += \
                g[max(0, -dr):h - max(0, dr), max(0, -dc):w - max(0, dc)]
        core = g & (deg >= 3)

    labels = np.full((h, w), -1, dtype=np.int32)
    rooms: List[Room] = []
    for r0 in range(h):
        for c0 in range(w):
            if not core[r0, c0] or labels[r0, c0] >= 0:
                continue
            idx = len(rooms)
            stack = [(r0, c0)]
            labels[r0, c0] = idx
            comp = []
            while stack:
                r, c = stack.pop()
                comp.append((r, c))
                for dr, dc in _NEIGHBORS4:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < h and 0 <= nc < w and core[nr, nc] and labels[nr, nc] < 0:
                        labels[nr, nc] = idx
                        stack.append((nr, nc))
            if len(comp) < min_core:
                for r, c in comp:
                    labels[r, c] = -1
                continue
            rs = [p[0] for p in comp]
            cs = [p[1] for p in comp]
            rooms.append(Room(idx=idx, x0=min(cs), z0=min(rs),
                              x1=max(cs) + 1, z1=max(rs) + 1))

    # 把每个房间的核心向外扩一圈：先到先得，走廊格保持未分配
    occupied = np.zeros((h, w), dtype=bool)
    for room in rooms:
        cells = []
        for r in range(max(0, room.z0 - 1), min(h, room.z1 + 1)):
            for c in range(max(0, room.x0 - 1), min(w, room.x1 + 1)):
                if g[r, c] and not occupied[r, c]:
                    occupied[r, c] = True
                    cells.append((r, c))
        room.cells = cells
        if cells:
            rs = [p[0] for p in cells]
            cs = [p[1] for p in cells]
            room.x0, room.x1 = min(cs), max(cs) + 1
            room.z0, room.z1 = min(rs), max(rs) + 1
    for i, room in enumerate(rooms):        # 跳过小核心时重新编号，保证 idx == 下标
        room.idx = i
    return rooms


def rooms_from_rects(grid, rects: Sequence[dict]) -> List[Room]:
    """用 BSP 给出的房间矩形（``x,y,w,h``）建房间列表。"""
    g = _as_grid(grid)
    h, w = g.shape
    rooms: List[Room] = []
    for i, rect in enumerate(rects):
        x0 = int(rect.get("x", 0))
        z0 = int(rect.get("y", 0))
        rw = int(rect.get("w", 0))
        rh = int(rect.get("h", 0))
        x1, z1 = min(w, x0 + rw), min(h, z0 + rh)
        x0, z0 = max(0, x0), max(0, z0)
        cells = [(r, c) for r in range(z0, z1) for c in range(x0, x1) if g[r, c]]
        if not cells:
            continue
        rooms.append(Room(idx=len(rooms), x0=x0, z0=z0, x1=x1, z1=z1, cells=cells))
    return rooms


def _simplify(points: Sequence[Tuple[int, int]]) -> List[List[float]]:
    """去掉共线中间点，返回 ``[[x, z], ...]``。"""
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


def _label_cells(grid: np.ndarray, rooms: Sequence[Room]) -> np.ndarray:
    """0 = 走廊（地板但不在房间里）, -1 = 墙, i+1 = 第 i 间房。"""
    labels = np.where(np.asarray(grid, dtype=bool), 0, -1).astype(np.int32)
    for i, room in enumerate(rooms):
        for r, c in room.cells:
            labels[r, c] = i + 1
    return labels


def _connect_rooms(labels: np.ndarray, rooms: Sequence[Room]) -> Dict[Tuple[int, int], dict]:
    """房间两两之间第一次接触的走廊路径（去重，保留较短的一条）。"""
    h, w = labels.shape
    edges: Dict[Tuple[int, int], dict] = {}
    for i, room in enumerate(rooms):
        dist = np.full((h, w), -1, dtype=np.int32)
        prev = np.full((h, w), -1, dtype=np.int64)
        q = deque()
        for r, c in room.cells:
            if labels[r, c] == i + 1:
                dist[r, c] = 0
                q.append((r, c))
        contacts: Dict[int, Tuple[int, int, int, int]] = {}
        while q:
            r, c = q.popleft()
            for dr, dc in _NEIGHBORS4:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < h and 0 <= nc < w):
                    continue
                lab = int(labels[nr, nc])
                if lab < 0 or lab == i + 1:
                    continue
                if lab > 0:
                    j = lab - 1
                    if j not in contacts:
                        # (走廊侧 r,c, 房间侧 nr,nc)：回溯从走廊侧开始，再把房间侧接上
                        contacts[j] = (r, c, nr, nc)
                    continue                      # 不穿过第三方房间
                if dist[nr, nc] >= 0:
                    continue
                dist[nr, nc] = dist[r, c] + 1
                prev[nr, nc] = r * w + c
                q.append((nr, nc))

        for j, (r, c, nr, nc) in contacts.items():
            key = (min(i, j), max(i, j))
            if key in edges:
                continue
            path = []
            pr, pc = r, c
            while pr >= 0:
                path.append((pr, pc))
                p = int(prev[pr, pc])
                if p < 0:
                    break
                pr, pc = divmod(p, w)
            path.reverse()
            path.append((nr, nc))                 # 跨进目标房间的那一格
            edges[key] = {"i": key[0], "j": key[1], "path": path}
    return edges


def _bfs_tree(n: int, adj: Dict[int, List[int]], root: int):
    """返回 (parent, depth, order)。"""
    parent = {root: None}
    depth = {root: 0}
    order = [root]
    q = deque([root])
    while q:
        u = q.popleft()
        for v in adj.get(u, []):
            if v not in parent:
                parent[v] = u
                depth[v] = depth[u] + 1
                order.append(v)
                q.append(v)
    return parent, depth, order


def build_dungeon_graph(grid, *, rooms: Optional[Sequence[dict]] = None,
                        locks: int = 1, loops: int = 2, seed: int = 0) -> dict:
    """从地牢网格抽出可解的关卡图。

    参数：
        rooms: BSP 的房间矩形列表；``None`` 则自动识别。
        locks: 需要上锁的生成树边数上限（0 = 不上锁）。
        loops: 额外加的回路边数上限（让地图有环，不是纯树）。
        seed:  同等条件下选哪几条边/哪间房放钥匙的随机种子。

    返回::

        {"nodes": [...], "edges": [...], "keys": [...],
         "entrance": id, "boss": id, "stats": {...}}

    ``nodes``/``edges`` 与 ``worldspec`` 的 ``graph.json`` 同形，可直接喂给
    下游的 ``MapGraph``。
    """
    g = _as_grid(grid)
    h, w = g.shape
    rng = np.random.RandomState(seed)

    rs = rooms_from_rects(g, rooms) if rooms is not None else detect_rooms(g)
    if not rs:
        return {"nodes": [], "edges": [], "keys": [], "entrance": None, "boss": None,
                "stats": {"rooms": 0, "edges": 0, "keys": 0, "loops": 0,
                          "note": "网格里没有认出房间（可能全是走廊）"}}

    labels = _label_cells(g, rs)
    raw_edges = _connect_rooms(labels, rs)

    # ---- 邻接（去重无向） ----
    adj: Dict[int, List[int]] = {i: [] for i in range(len(rs))}
    for (i, j) in raw_edges:
        adj[i].append(j)
        adj[j].append(i)

    # ---- 入口：贴边优先，其次离边最近，再按面积/编号稳定排序 ----
    def border_dist(room: Room) -> int:
        return min(room.x0, room.z0, w - room.x1, h - room.z1)

    entrance = min(rs, key=lambda r: (border_dist(r), -r.area, r.idx)).idx

    parent, depth, _order = _bfs_tree(len(rs), adj, entrance)
    tree_edges = {(min(v, parent[v]), max(v, parent[v]))
                  for v in parent if parent[v] is not None}

    # ---- 先决定哪些是回路（非树边，按路径短优先） ----
    loop_candidates = sorted((e for e in raw_edges if (e[0], e[1]) not in tree_edges),
                             key=lambda e: (len(raw_edges[e]["path"]), e))
    loop_keys = set(loop_candidates[:max(0, int(loops))])

    # ---- 再挑锁：只在生成树上、且子树不含入口的深层边 ----
    def subtree(child: int, blocked: Tuple[int, int]) -> List[int]:
        seen = {child}
        q = deque([child])
        while q:
            u = q.popleft()
            for v in adj.get(u, []):
                if (min(u, v), max(u, v)) == blocked or v in seen:
                    continue
                seen.add(v)
                q.append(v)
        return list(seen)

    lock_candidates = []
    for (a, b) in tree_edges:
        child = a if parent.get(a) == b else b
        if parent.get(child) is None:
            continue
        sub = subtree(child, (a, b))
        if entrance in sub or len(sub) == 0:
            continue
        lock_candidates.append((depth.get(child, 0), child, (a, b), sub))
    lock_candidates.sort(key=lambda t: (-t[0], t[1]))

    locked: Dict[Tuple[int, int], dict] = {}
    locked_rooms = set()
    for dep, child, key, sub in lock_candidates:
        if len(locked) >= max(0, int(locks)):
            break
        if any(r in locked_rooms for r in sub):
            continue                                  # 避免锁套锁，钥匙位置难验
        locked[key] = {"child": child, "depth": dep, "subtree": sub,
                       "key_room": None}
        locked_rooms.update(sub)

    # ---- 钥匙：必须在「不经过任何锁」就能从入口到达的房间里 ----
    def reachable_without_locks() -> set:
        seen = {entrance}
        q = deque([entrance])
        while q:
            u = q.popleft()
            for v in adj.get(u, []):
                if (min(u, v), max(u, v)) in locked:
                    continue
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        return seen

    keys: List[dict] = []
    for key, info in locked.items():
        safe = sorted(reachable_without_locks() - locked_rooms)
        if not safe:
            continue
        pool = [r for r in safe if depth.get(r, 0) <= max(0, info["depth"] - 1)] or safe
        room = int(pool[rng.randint(len(pool))])
        key_id = f"key-{len(keys):02d}"
        info["key_room"] = room
        keys.append({"id": key_id, "room": rs[room].id(),
                     "unlocks": [f"{rs[key[0]].id()}--{rs[key[1]].id()}"]})
        rs[room].tags.append("key")

    # ---- 语义标注 ----
    boss = max(depth, key=lambda r: (depth[r], r)) if depth else entrance
    rs[entrance].tags.append(KIND_ENTRANCE)
    if boss != entrance:
        rs[boss].tags.append(KIND_BOSS)

    # 宝箱：优先放在被锁住的子树里最深的房间
    treasure_rooms = [r for r in locked_rooms if r != boss and r != entrance]
    for r in sorted(treasure_rooms, key=lambda r: (-depth.get(r, 0), r))[:2]:
        rs[r].tags.append(KIND_TREASURE)

    # 守卫：入口→Boss 路径上的中间房间（最多 2 个）
    path_to_boss: List[int] = []
    cur = boss
    while cur is not None and cur != entrance:
        path_to_boss.append(cur)
        cur = parent.get(cur)
    guards = [r for r in reversed(path_to_boss) if r not in (boss, entrance)][:2]
    for r in guards:
        rs[r].tags.append(KIND_GUARD)

    # ---- 输出 ----
    nodes = []
    for room in rs:
        x, z = room.center
        kind = KIND_ROOM
        for tag in (KIND_ENTRANCE, KIND_BOSS, KIND_TREASURE, KIND_GUARD):
            if tag in room.tags:
                kind = tag
                break
        nodes.append({
            "id": room.id(), "kind": kind, "x": float(x), "z": float(z),
            "name": room.id(), "score": float(room.area),
            "meta": {"bbox": [room.x0, room.z0, room.x1, room.z1],
                     "area": room.area, "depth": int(depth.get(room.idx, 0)),
                     "tags": list(dict.fromkeys(room.tags))},
        })

    edges = []
    for (i, j), info in raw_edges.items():
        key = (i, j)
        if key in locked:
            kind = EDGE_LOCKED
        elif key in loop_keys:
            kind = EDGE_LOOP
        else:
            kind = EDGE_OPEN
        pts = _simplify(info["path"])
        ci, cj = rs[i].center, rs[j].center
        pts = [[float(ci[0]), float(ci[1])]] + pts + [[float(cj[0]), float(cj[1])]]
        edges.append({
            "a": rs[i].id(), "b": rs[j].id(), "kind": kind,
            "length": float(len(info["path"])),
            "straight": float(abs(ci[0] - cj[0]) + abs(ci[1] - cj[1])),
            "cost": float(len(info["path"])),
            "points": pts,
            "key": next((k["id"] for k in keys
                         if k["room"] == rs[locked[key]["key_room"]].id()), None)
            if key in locked and locked[key]["key_room"] is not None else None,
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "keys": keys,
        "entrance": rs[entrance].id(),
        "boss": rs[boss].id(),
        "stats": {"rooms": len(rs), "edges": len(edges), "keys": len(keys),
                  "loops": len(loop_keys), "locks": len(locked),
                  "max_depth": int(max(depth.values())) if depth else 0,
                  "grid": [int(h), int(w)]},
    }


def to_ascii(graph: dict, grid) -> str:
    """把图叠在网格上打出来（调试用；POI 以首字母标记）。"""
    g = np.asarray(grid)
    marks: Dict[Tuple[int, int], str] = {}
    for node in graph.get("nodes", []):
        bbox = (node.get("meta") or {}).get("bbox")
        if not bbox:
            continue
        x0, z0, x1, z1 = bbox
        r, c = (z0 + z1 - 1) // 2, (x0 + x1 - 1) // 2
        kind = node.get("kind", "room")
        marks[(int(r), int(c))] = {
            KIND_ENTRANCE: "E", KIND_BOSS: "B",
            KIND_TREASURE: "$", KIND_GUARD: "G",
        }.get(kind, "·")
    out = []
    for r in range(g.shape[0]):
        row = []
        for c in range(g.shape[1]):
            row.append(marks.get((r, c), "#" if not g[r, c] else " "))
        out.append("".join(row))
    return "\n".join(out)
