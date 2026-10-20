"""路网测试：连通性、几何保真、绕行上限、过河点必须在水上。

路网最容易坏在两处：一是点连不齐（有孤岛），二是"路"其实是贴着悬崖的直线。
这里用**图连通 + 绕行比 + 端点坐标**三条硬断言把这两种情况都钉住。
"""

from collections import defaultdict

import numpy as np
import pytest

import worldbuilder as wb


@pytest.fixture(scope="module")
def world():
    return wb.generate_world_full(96, 96, seed=7, falloff=0.35)


@pytest.fixture(scope="module")
def net(world):
    pois = wb.place_pois(world, seed=7)
    return wb.build_road_network(pois, world, seed=7)


def _adjacency(edges):
    adj = defaultdict(set)
    for e in edges:
        adj[e["a"]].add(e["b"])
        adj[e["b"]].add(e["a"])
    return adj


def test_all_settlements_connected(world, net):
    adj = _adjacency(net["edges"])
    settlements = [p.id for p in wb.place_pois(world, seed=7)
                   if p.kind in wb.SETTLEMENT_KINDS]
    assert len(settlements) >= 2
    seen = {settlements[0]}
    stack = [settlements[0]]
    while stack:
        for nb in adj[stack.pop()]:
            if nb not in seen:
                seen.add(nb)
                stack.append(nb)
    missing = [s for s in settlements if s not in seen]
    assert not missing, f"这些聚落没连上：{missing}"


def test_edge_endpoints_are_nodes(net):
    ids = {n["id"] for n in net["nodes"]}
    for e in net["edges"]:
        assert e["a"] in ids and e["b"] in ids
        assert e["a"] != e["b"]


def test_edge_geometry_starts_and_ends_at_pois(net):
    by_id = {n["id"]: n for n in net["nodes"]}
    for e in net["edges"]:
        a, b = by_id[e["a"]], by_id[e["b"]]
        pts = e["points"]
        assert len(pts) >= 2
        assert pts[0] == [a["x"], a["z"]], f"{e['a']} 起点不对"
        assert pts[-1] == [b["x"], b["z"]], f"{e['b']} 终点不对"


def test_edge_length_not_shorter_than_straight(net):
    for e in net["edges"]:
        assert e["length"] >= e["straight"] - 1e-6
        assert e["cost"] > 0


def test_detour_reasonable(net):
    # 绕行比 = 实际路长 / 直线距离。超过 3 说明路在乱绕（或端点被海隔开）
    assert net["stats"]["detour"] < 3.0, net["stats"]


def test_crossings_sit_on_water(world, net):
    water = world["water"]
    for c in net["crossings"]:
        w = water[int(c["z"]), int(c["x"])]
        assert w in (1, 2), f"{c['id']} 不在河/湖上（water={w}）"
        assert c["kind"] in (wb.KIND_BRIDGE, wb.KIND_FORD)


def test_road_mask_covers_endpoints(net):
    mask = net["mask"]
    for n in net["nodes"]:
        if n["kind"] in wb.SETTLEMENT_KINDS:
            assert mask[int(n["z"]), int(n["x"])], f"{n['id']} 不在路网上"


def test_least_cost_path_stays_passable(world):
    # 端点必须落在主陆块上——随手写的坐标很可能在海上，那本来就该返回 None
    main = wb.poi.main_landmass(world["water"])
    cells = np.argwhere(main)
    assert len(cells) > 10
    a, b = cells[0], cells[-1]
    cost = wb.road_cost_field(world)
    path = wb.least_cost_path(cost, tuple(a), tuple(b))
    assert path, "同一陆块内应能找到路"
    for r, c in path:
        assert np.isfinite(cost[r, c]), f"路径经过不可通行格 ({r},{c})"


def test_blocked_goal_returns_none():
    cost = np.ones((20, 20))
    cost[:, 10] = np.inf                     # 一道无限高的墙
    assert wb.least_cost_path(cost, (5, 5), (5, 15)) is None


def test_diagonal_corner_not_cut():
    # 起点 (2,2) 到 (3,3)：正对角被 (2,3) 堵住，不允许斜穿
    cost = np.ones((6, 6))
    cost[2, 3] = np.inf
    path = wb.least_cost_path(cost, (2, 2), (3, 3))
    assert path is not None
    assert len(path) == 3, f"应绕两格，实际走了 {len(path)} 个格"
    # 每一步必须是 8 邻接的单格移动
    for (r1, c1), (r2, c2) in zip(path, path[1:]):
        assert max(abs(r2 - r1), abs(c2 - c1)) == 1


def test_build_with_single_settlement_is_safe(world):
    pois = wb.place_pois(world, seed=7, settlements=1, ports=0, mines=0,
                         ruins=0, lighthouses=0)
    net = wb.build_road_network(pois, world)
    assert net["edges"] == []
    assert net["stats"]["edges"] == 0
