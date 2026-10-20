"""WFC 测试：局部规则的**全局一致性**是唯一要钉的东西。

WFC 的输出看起来随机，但必须满足两条机械判据：
每一对相邻瓦片的共享边标志相等；栅格化后的地板单连通。
剩下的（好不好看）不测。
"""

import numpy as np
import pytest

import worldbuilder as wb


def _floor_components(grid):
    h, w = grid.shape
    seen = np.zeros((h, w), dtype=bool)
    sizes = []
    for r0 in range(h):
        for c0 in range(w):
            if not grid[r0, c0] or seen[r0, c0]:
                continue
            stack = [(r0, c0)]
            seen[r0, c0] = True
            n = 0
            while stack:
                r, c = stack.pop()
                n += 1
                for dr, dc in ((0, 1), (-1, 0), (0, -1), (1, 0)):
                    nr, nc = r + dr, c + dc
                    if (0 <= nr < h and 0 <= nc < w and grid[nr, nc]
                            and not seen[nr, nc]):
                        seen[nr, nc] = True
                        stack.append((nr, nc))
            sizes.append(n)
    return sizes


def test_wang_edges_match_between_neighbors():
    ts = wb.wang_tileset()
    tiles = wb.generate_wfc(20, 15, ts, seed=1)
    assert tiles.shape == (15, 20)
    for r in range(tiles.shape[0]):
        for c in range(tiles.shape[1]):
            t = ts.tiles[int(tiles[r, c])]
            if c + 1 < tiles.shape[1]:
                right = ts.tiles[int(tiles[r, c + 1])]
                assert t.edges[1] == right.edges[3], f"({r},{c}) 东边不匹配"
            if r + 1 < tiles.shape[0]:
                down = ts.tiles[int(tiles[r + 1, c])]
                assert t.edges[2] == down.edges[0], f"({r},{c}) 南边不匹配"


def test_no_isolated_tile():
    ts = wb.wang_tileset()
    tiles = wb.generate_wfc(12, 12, ts, seed=2)
    for t in tiles.ravel():
        assert sum(ts.tiles[int(t)].edges) >= 1, "不应出现四边全不通的死格"


def test_dungeon_shape_and_connectivity():
    d = wb.generate_dungeon_wfc(24, 16, seed=3)
    grid = d["grid"]
    assert grid.shape == (16 * 3, 24 * 3)
    assert grid.dtype == np.uint8
    assert grid.sum() > 0
    comps = _floor_components(grid)
    assert len(comps) == 1, f"地板应单连通，实际 {len(comps)} 块"


def test_dungeon_floor_ratio_sane():
    d = wb.generate_dungeon_wfc(32, 24, seed=11)
    ratio = float(d["grid"].mean())
    assert 0.05 < ratio < 0.55, f"地板占比 {ratio:.2f} 不像地牢"


def test_deterministic_per_seed():
    a = wb.generate_dungeon_wfc(16, 12, seed=5)["tiles"]
    b = wb.generate_dungeon_wfc(16, 12, seed=5)["tiles"]
    assert np.array_equal(a, b)


def test_different_seed_differs():
    a = wb.generate_dungeon_wfc(16, 12, seed=5)["tiles"]
    b = wb.generate_dungeon_wfc(16, 12, seed=6)["tiles"]
    assert not np.array_equal(a, b)


def test_contradiction_raises():
    # A 的东边是 1、B 的西边是 2，互不匹配，且没有别的瓦片可用 → 无解
    ts = wb.TileSet([wb.Tile("A", (0, 1, 0, 0)), wb.Tile("B", (0, 2, 0, 0))])
    with pytest.raises(wb.WfcContradiction):
        wb.generate_wfc(2, 1, ts, seed=0)


def test_explicit_adjacency_checkerboard():
    # 显式规则：P 旁边只能 Q、Q 旁边只能 P → 6x6 必须严格交替
    tiles = [wb.Tile("P"), wb.Tile("Q")]
    adj = {(i, d): [1 - i] for i in range(2) for d in range(4)}
    ts = wb.TileSet(tiles, adjacency=adj)
    g = wb.generate_wfc(6, 6, ts, seed=0)
    for r in range(6):
        for c in range(6):
            if c + 1 < 6:
                assert g[r, c] != g[r, c + 1]
            if r + 1 < 6:
                assert g[r, c] != g[r + 1, c]


def test_max_cells_guard():
    ts = wb.wang_tileset()
    with pytest.raises(ValueError):
        wb.generate_wfc(400, 400, ts, max_cells=1000)


def test_weights_bias_distribution():
    # 死胡同权重拉开两个量级，出现频率必须跟着变（同 seed 比较更稳）
    low = wb.wang_tileset(dead_end_weight=0.01)
    high = wb.wang_tileset(dead_end_weight=5.0)

    def dead_end_ratio(ts, seed=4):
        tiles = wb.generate_wfc(24, 24, ts, seed=seed)
        counts = [sum(ts.tiles[int(t)].edges) for t in tiles.ravel()]
        return counts.count(1) / len(counts)

    assert dead_end_ratio(high) > dead_end_ratio(low)
