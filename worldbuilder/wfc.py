"""瓦片级 Wave Function Collapse（约束传播 + 有限回溯）。

与「按 BSP / CA 硬生成房间」不同，WFC 的输入是**局部兼容规则**，输出是满足
规则的任意全局布局——这让地牢既不会每次都长得一样，又不会出现"走廊断头""门对着墙"
这类结构性错误。

本实现的规则来源有两条：

1. **边匹配（Wang 瓦片）**：每个瓦片四条边各带一个整数，相邻瓦片的共享边必须相等。
   ``wang_tileset()`` 用 4 个布尔通道（N/E/S/W 是否有通路）生成 15 个瓦片，
   这保证"有通路的一侧，对面也一定有通路"。
2. **显式邻接**：``TileSet(tiles, adjacency={(tile, dir): {tile, ...}})``，
   用于表达"某瓦片旁边不许出现某瓦片"这种非几何约束。

算法是标准 WFCF：

- 每个格子维护一个**候选位集**（Python int，位 i 表示第 i 个瓦片仍可能）；
- 每次挑候选最少的格子塌缩（按瓦片权重加权随机），然后做**弧相容传播**；
- 传播出现空集 = 矛盾，按决策栈回退（chronological backtracking），
  把上次选的瓦片从该格候选里剔掉再试。

规模限制：候选扫描用惰性堆（熵变化时压入新条目，弹出时校验），
但传播本身是 Python 循环，``max_cells`` 默认 40,000（200×200）用于兜底。
地牢尺寸（几十×几十）远低于此。

瓦片朝向约定：``edges = (N, E, S, W)``，方向顺序与 ``DIRS`` 一致（上、右、下、左）。
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np

#: 方向：0=N(-1,0) 1=E(0,1) 2=S(+1,0) 3=W(0,-1)
DIRS: Tuple[Tuple[int, int], ...] = ((-1, 0), (0, 1), (1, 0), (0, -1))
_OPPOSITE: Tuple[int, int, int, int] = (2, 3, 0, 1)

#: 一个瓦片栅格化成多少×多少格
TILE_CELLS = 3


class WfcContradiction(RuntimeError):
    """规则集无解（或回溯耗尽）。"""


@dataclass(frozen=True)
class Tile:
    """一个瓦片。

    ``edges`` 是四条边的"接口编号"：相邻瓦片共享边时，本瓦片的 ``edges[d]``
    必须等于邻居的 ``edges[对向]``。用 0/1 就是"有没有通路"，用 2/3/4 可以表达
    "路面/水面/轨道"这类不同连接材质。
    """

    name: str
    edges: Tuple[int, int, int, int] = (0, 0, 0, 0)
    weight: float = 1.0
    payload: dict = field(default_factory=dict, compare=False, hash=False)

    def __repr__(self) -> str:                       # pragma: no cover - 调试用
        return f"Tile({self.name}, edges={self.edges})"


class TileSet:
    """瓦片集合 + 兼容规则（预编译成位掩码，传播时只做位运算）。"""

    def __init__(self, tiles: Sequence[Tile], *,
                 adjacency: Optional[Dict[Tuple[int, int], Iterable[int]]] = None):
        self.tiles: List[Tile] = list(tiles)
        if not self.tiles:
            raise ValueError("TileSet 至少需要一个瓦片")
        n = self.n = len(self.tiles)
        compat = [[0] * n for _ in range(4)]

        if adjacency is not None:
            for (i, d), js in adjacency.items():
                if not (0 <= i < n and 0 <= d < 4):
                    raise ValueError(f"adjacency 键越界：({i}, {d})")
                for j in js:
                    compat[d][i] |= 1 << j
        else:
            for d in range(4):
                for i in range(n):
                    want = self.tiles[i].edges[d]
                    m = 0
                    for j in range(n):
                        if self.tiles[j].edges[_OPPOSITE[d]] == want:
                            m |= 1 << j
                    compat[d][i] = m
        self._compat = compat
        self._support: Dict[Tuple[int, int], int] = {}

    @property
    def full_domain(self) -> int:
        return (1 << self.n) - 1

    def support(self, direction: int, domain: int) -> int:
        """给定本格候选集，返回邻居在该方向上仍允许的候选集（带缓存）。"""
        key = (direction, domain)
        cached = self._support.get(key)
        if cached is not None:
            return cached
        out = 0
        m = domain
        col = self._compat[direction]
        while m:
            low = m & -m
            out |= col[low.bit_length() - 1]
            m ^= low
        self._support[key] = out
        return out

    def tile_of(self, domain: int) -> int:
        return domain.bit_length() - 1

    def __len__(self) -> int:
        return self.n


def wang_tileset(*, dead_end_weight: float = 0.35, straight_weight: float = 1.0,
                 corner_weight: float = 1.0, tee_weight: float = 0.6,
                 cross_weight: float = 0.45) -> TileSet:
    """15 个王瓦片（4 边通/不通，排除四边全不通的死格）。

    权重按"通道数"分组：直道/转角最常见，丁字路口次之，十字最少，死胡同罕见。
    权重只影响分布，不影响合法性——想要更多死胡同就调大 ``dead_end_weight``。
    """
    tiles: List[Tile] = []
    for mask in range(1, 16):
        flags = tuple((mask >> i) & 1 for i in range(4))       # N E S W
        count = sum(flags)
        if count == 1:
            w = dead_end_weight
        elif count == 2:
            straight = flags in ((1, 0, 1, 0), (0, 1, 0, 1))
            w = straight_weight if straight else corner_weight
        elif count == 3:
            w = tee_weight
        else:
            w = cross_weight
        name = "".join(f"{c}{flags[i]}" for i, c in enumerate("NESW"))
        tiles.append(Tile(name=name, edges=flags, weight=w))
    return TileSet(tiles)


def _weighted_pick(ts: TileSet, domain: int, rng: np.random.RandomState) -> int:
    idx: List[int] = []
    w: List[float] = []
    m = domain
    while m:
        low = m & -m
        i = low.bit_length() - 1
        idx.append(i)
        w.append(max(float(ts.tiles[i].weight), 0.0))
        m ^= low
    total = sum(w)
    if total <= 0.0:
        return int(idx[rng.randint(len(idx))])
    p = np.asarray(w, dtype=np.float64) / total
    return int(idx[rng.choice(len(idx), p=p)])


def generate_wfc(width: int, height: int, tileset: TileSet, *, seed: int = 0,
                 max_cells: int = 40_000, max_collapses: Optional[int] = None,
                 max_backtracks: int = 20_000) -> np.ndarray:
    """生成 ``(height, width)`` 的瓦片索引网格（``int16``）。

    抛 ``WfcContradiction`` 表示这组规则在给定尺寸下无解（或回溯预算耗尽）。
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"尺寸必须为正，收到 {width}x{height}")
    if width * height > max_cells:
        raise ValueError(f"{width}x{height} 超过 max_cells={max_cells}；"
                         "传播是纯 Python 循环，请分块生成")
    n = len(tileset)
    full = tileset.full_domain
    rng = np.random.RandomState(seed)
    cells = [[full] * width for _ in range(height)]
    trail: List[Tuple[int, int, int]] = []
    decisions: List[Tuple[int, int, int, int, int]] = []   # r, c, 原域, trail 标记, 选中
    tie = itertools.count()
    heap: List[Tuple[int, int, int, int]] = [(n, next(tie), r, c)
                                             for r in range(height) for c in range(width)]
    heapq.heapify(heap)

    def propagate(seeds: Sequence[Tuple[int, int]]) -> bool:
        stack = list(seeds)
        while stack:
            r, c = stack.pop()
            dom = cells[r][c]
            if dom == 0:
                return False
            for d, (dr, dc) in enumerate(DIRS):
                nr, nc = r + dr, c + dc
                if not (0 <= nr < height and 0 <= nc < width):
                    continue
                cur = cells[nr][nc]
                new = cur & tileset.support(d, dom)
                if new != cur:
                    if new == 0:
                        return False
                    trail.append((nr, nc, cur))
                    cells[nr][nc] = new
                    heapq.heappush(heap, (new.bit_count(), next(tie), nr, nc))
                    stack.append((nr, nc))
        return True

    collapses = 0
    backtracks = 0
    limit = max_collapses if max_collapses is not None else width * height * 40

    while True:
        cell = None
        while heap:
            entropy, _t, r, c = heapq.heappop(heap)
            dom = cells[r][c]
            if dom == 0:
                raise WfcContradiction(f"格 ({r},{c}) 候选为空")
            if dom.bit_count() != entropy or entropy <= 1:
                continue                                  # 惰性条目
            cell = (r, c)
            break
        if cell is None:
            break

        r, c = cell
        dom = cells[r][c]
        chosen = _weighted_pick(tileset, dom, rng)
        mark = len(trail)
        cells[r][c] = 1 << chosen
        trail.append((r, c, dom))
        decisions.append((r, c, dom, mark, chosen))
        collapses += 1
        if collapses > limit:
            raise WfcContradiction(f"塌缩次数超过上限 {limit}（疑似规则导致死循环）")

        if propagate([(r, c)]):
            continue

        # ---- 回溯：撤到上一个决策点，把它的选择从候选里剔掉再试 ----
        resolved = False
        while decisions:
            br, bc, bdom, bmark, bchosen = decisions.pop()
            while len(trail) > bmark:
                rr, cc, old = trail.pop()
                cells[rr][cc] = old
            backtracks += 1
            if backtracks > max_backtracks:
                raise WfcContradiction(f"回溯次数超过上限 {max_backtracks}")
            reduced = bdom & ~(1 << bchosen)
            if reduced == 0:
                continue
            pick2 = _weighted_pick(tileset, reduced, rng)
            mark2 = len(trail)
            cells[br][bc] = 1 << pick2
            trail.append((br, bc, reduced))
            decisions.append((br, bc, reduced, mark2, pick2))
            heapq.heappush(heap, (1, next(tie), br, bc))
            if propagate([(br, bc)]):
                resolved = True
                break
        if not resolved:
            raise WfcContradiction("规则集矛盾且回溯耗尽：没有任何合法铺法")

    out = np.full((height, width), -1, dtype=np.int16)
    for r in range(height):
        for c in range(width):
            dom = cells[r][c]
            if dom.bit_count() != 1:
                raise WfcContradiction(f"格 ({r},{c}) 未收敛到唯一瓦片")
            out[r, c] = dom.bit_length() - 1
    return out


def _largest_component(grid: np.ndarray) -> np.ndarray:
    """只保留最大的 4 连通地板连通块（其余填 0）。"""
    h, w = grid.shape
    seen = np.zeros((h, w), dtype=bool)
    best: List[Tuple[int, int]] = []
    for r0 in range(h):
        for c0 in range(w):
            if not grid[r0, c0] or seen[r0, c0]:
                continue
            stack = [(r0, c0)]
            seen[r0, c0] = True
            comp: List[Tuple[int, int]] = []
            while stack:
                r, c = stack.pop()
                comp.append((r, c))
                for dr, dc in DIRS:
                    nr, nc = r + dr, c + dc
                    if (0 <= nr < h and 0 <= nc < w and grid[nr, nc]
                            and not seen[nr, nc]):
                        seen[nr, nc] = True
                        stack.append((nr, nc))
            if len(comp) > len(best):
                best = comp
    out = np.zeros_like(grid)
    for r, c in best:
        out[r, c] = 1
    return out


def rasterize(tiles: np.ndarray, tileset: TileSet, *,
              keep_largest: bool = True, cell: int = TILE_CELLS) -> np.ndarray:
    """瓦片网格 → 1/0 栅格（1=地板、0=墙，与本仓 ``dungeon`` 的约定一致）。

    每个瓦片占 ``cell × cell`` 格：中心永远是地板，四个方向的通路各点亮边中点的一格。
    由于边标志在相邻瓦片间相等，两侧的边中点格**天然相邻**，所以地板连通性
    与瓦片连接性完全一致——不需要额外的"缝合"步骤。

    ``keep_largest=True`` 会丢弃 WFC 生成的孤立区域（王瓦片允许出现互不相连的
    走廊群），保证输出是一张"从任意地板都能走到任意地板"的地图。
    """
    h, w = tiles.shape
    grid = np.zeros((h * cell, w * cell), dtype=np.uint8)
    mid = cell // 2
    for r in range(h):
        for c in range(w):
            t = tileset.tiles[int(tiles[r, c])]
            r0, c0 = r * cell, c * cell
            grid[r0 + mid, c0 + mid] = 1
            if t.edges[0]:
                grid[r0, c0 + mid] = 1
            if t.edges[1]:
                grid[r0 + mid, c0 + cell - 1] = 1
            if t.edges[2]:
                grid[r0 + cell - 1, c0 + mid] = 1
            if t.edges[3]:
                grid[r0 + mid, c0] = 1
    return _largest_component(grid) if keep_largest else grid


def generate_dungeon_wfc(width: int = 32, height: int = 24, *, seed: int = 0,
                         tileset: Optional[TileSet] = None,
                         keep_largest: bool = True) -> dict:
    """WFC 地牢：返回 ``{"grid", "tiles", "tile_names", "seed"}``。

    ``grid`` 是 ``(height*3, width*3)`` 的 uint8（1=地板），可直接喂给
    ``dungeon.to_ascii`` 或 3dworld 的体素网格化。
    """
    ts = tileset or wang_tileset()
    tiles = generate_wfc(width, height, ts, seed=seed)
    grid = rasterize(tiles, ts, keep_largest=keep_largest)
    return {"grid": grid, "tiles": tiles,
            "tile_names": [t.name for t in ts.tiles], "seed": int(seed)}
