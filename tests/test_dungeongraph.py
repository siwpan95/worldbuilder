"""地牢图测试：**可解性**是唯一不能妥协的性质。

一组锁钥如果让玩家"先拿到钥匙才能开门、而钥匙在门后"，关卡就是死的。
这里用图论硬判据钉住：每把钥匙所在房间，必须在不经过任何锁的情况下可达。
"""

from collections import deque

import numpy as np
import pytest

import worldbuilder as wb
from worldbuilder import dungeongraph as DG


@pytest.fixture(scope="module")
def bsp():
    d = wb.generate_dungeon_bsp(48, 32, seed=5)
    return d, DG.build_dungeon_graph(d["grid"], rooms=d["rooms"], locks=2, loops=2, seed=3)


def _adj(graph, *, skip_locked=False):
    adj = {n["id"]: set() for n in graph["nodes"]}
    for e in graph["edges"]:
        if skip_locked and e["kind"] == DG.EDGE_LOCKED:
            continue
        adj[e["a"]].add(e["b"])
        adj[e["b"]].add(e["a"])
    return adj


def _dist(graph, start, *, skip_locked=False):
    adj = _adj(graph, skip_locked=skip_locked)
    dist = {start: 0}
    q = deque([start])
    while q:
        u = q.popleft()
        for v in adj.get(u, ()):
            if v not in dist:
                dist[v] = dist[u] + 1
                q.append(v)
    return dist


def test_bsp_all_rooms_become_nodes(bsp):
    d, g = bsp
    assert len(g["nodes"]) == len(d["rooms"])
    assert g["stats"]["rooms"] == len(d["rooms"])


def test_graph_connected(bsp):
    _d, g = bsp
    # 连通性按"所有边都算"判（锁只是要钥匙，不是断路）。
    # 跳过错边后必然断开——那是锁的作用，由 test_keys_reachable_without_any_lock 管。
    dist = _dist(g, g["entrance"])
    assert set(dist) == {n["id"] for n in g["nodes"]}, "整张图必须连通"


def test_entrance_is_closest_to_border(bsp):
    # BSP 的房间带边距，不贴边；入口的定义是"离边界最近"的那个
    d, g = bsp
    by_id = {n["id"]: n for n in g["nodes"]}
    h, w = d["grid"].shape

    def border_dist(nid):
        x0, z0, x1, z1 = by_id[nid]["meta"]["bbox"]
        return min(x0, z0, w - x1, h - z1)

    assert border_dist(g["entrance"]) == min(border_dist(n["id"]) for n in g["nodes"])


def test_boss_is_farthest_from_entrance(bsp):
    _d, g = bsp
    dist = _dist(g, g["entrance"])
    assert dist[g["boss"]] == max(dist.values())


def test_keys_reachable_without_any_lock(bsp):
    """核心不变量：钥匙必须能在"一道锁都不开"的情况下拿到。"""
    _d, g = bsp
    safe = set(_dist(g, g["entrance"], skip_locked=True))
    assert g["keys"], "locks=2 时应该至少放出一把钥匙"
    for k in g["keys"]:
        assert k["room"] in safe, f"{k['id']} 放在锁后面了：{k['room']}"


def test_locked_edges_point_to_existing_key(bsp):
    _d, g = bsp
    keys = {k["id"] for k in g["keys"]}
    locked = [e for e in g["edges"] if e["kind"] == DG.EDGE_LOCKED]
    assert locked
    for e in locked:
        assert e["key"] in keys, f"锁边 {e['a']}--{e['b']} 没有对应钥匙"


def test_loops_create_cycles(bsp):
    _d, g = bsp
    # 3 个环 == 生成树边数 + 3；这里只断言"边数多于树"，且存在 loop 边
    assert any(e["kind"] == DG.EDGE_LOOP for e in g["edges"])
    assert len(g["edges"]) > len(g["nodes"]) - 1


def test_deterministic(bsp):
    d, g = bsp
    again = DG.build_dungeon_graph(d["grid"], rooms=d["rooms"], locks=2, loops=2, seed=3)
    assert [n["id"] for n in again["nodes"]] == [n["id"] for n in g["nodes"]]
    assert [(e["a"], e["b"], e["kind"]) for e in again["edges"]] == \
           [(e["a"], e["b"], e["kind"]) for e in g["edges"]]


def test_edge_geometry_endpoints_match_nodes(bsp):
    _d, g = bsp
    by_id = {n["id"]: n for n in g["nodes"]}
    for e in g["edges"]:
        assert e["a"] in by_id and e["b"] in by_id
        assert e["points"][0] == [by_id[e["a"]]["x"], by_id[e["a"]]["z"]]
        assert e["points"][-1] == [by_id[e["b"]]["x"], by_id[e["b"]]["z"]]


def test_wfc_dungeon_gets_a_graph():
    d = wb.generate_dungeon_wfc(20, 14, seed=4)
    g = DG.build_dungeon_graph(d["grid"], locks=1, loops=2, seed=1)
    assert g["stats"]["rooms"] > 0
    assert g["edges"]
    assert g["entrance"] in {n["id"] for n in g["nodes"]}


def test_empty_grid_returns_empty_graph():
    g = DG.build_dungeon_graph(np.zeros((8, 8), dtype=np.uint8))
    assert g["nodes"] == [] and g["edges"] == [] and g["entrance"] is None


def test_ascii_matches_grid_size(bsp):
    d, g = bsp
    text = DG.to_ascii(g, d["grid"])
    lines = text.splitlines()
    assert len(lines) == d["grid"].shape[0]
    assert all(len(line) == d["grid"].shape[1] for line in lines)


def test_rooms_can_be_custom_rects():
    # 两间房 + 一条走廊的手工网格
    grid = np.zeros((12, 20), dtype=np.uint8)
    grid[2:6, 2:6] = 1
    grid[2:6, 14:18] = 1
    grid[4, 6:14] = 1
    g = DG.build_dungeon_graph(grid, locks=0, loops=0, seed=0)
    assert g["stats"]["rooms"] == 2
    assert len(g["edges"]) == 1
    assert g["edges"][0]["kind"] == DG.EDGE_OPEN
