"""POI 选址测试：选址约束是"地形上讲得通"的机械判据。

这些断言不测"好不好看"，只测**不能违反的硬约束**：
不能选在水里、不能违反间距、港口必须靠海、同 seed 必须逐位可复现。
"""

from collections import Counter

import numpy as np
import pytest

import worldbuilder as wb
from worldbuilder import poi as P


@pytest.fixture(scope="module")
def world():
    return wb.generate_world_full(96, 96, seed=7, falloff=0.35)


def _neighbors4(shape, r, c):
    for dr, dc in ((0, 1), (-1, 0), (0, -1), (1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < shape[0] and 0 <= nc < shape[1]:
            yield nr, nc


def test_all_pois_on_land(world):
    pois = wb.place_pois(world, seed=7)
    assert pois, "96² 世界应至少选出几个点"
    water = world["water"]
    for p in pois:
        assert water[int(p.z), int(p.x)] == 0, f"{p.id} 落在水面上"


def test_min_spacing_respected(world):
    spacing = 8
    pois = wb.place_pois(world, seed=7, spacing=spacing)
    pts = [(p.x, p.z) for p in pois]
    # 矿/遗迹/灯塔用 spacing//2 的抑制半径，所以全局下界取一半
    floor = (spacing // 2) ** 2
    for i, (x1, z1) in enumerate(pts):
        for x2, z2 in pts[i + 1:]:
            d2 = (x1 - x2) ** 2 + (z1 - z2) ** 2
            assert d2 >= floor - 1e-9, f"两个 POI 距离平方 {d2} < {floor}"


def test_ports_touch_sea(world):
    pois = wb.place_pois(world, seed=7)
    sea = world["water"] == 3
    ports = [p for p in pois if p.kind == wb.KIND_PORT]
    assert ports, "有海岸就该选出港口"
    for p in ports:
        r, c = int(p.z), int(p.x)
        assert any(sea[nr, nc] for nr, nc in _neighbors4(sea.shape, r, c)), f"{p.id} 不临海"


def test_settlement_kinds_and_counts(world):
    pois = wb.place_pois(world, seed=7, settlements=6, ports=2, mines=2,
                         ruins=2, lighthouses=1)
    kinds = Counter(p.kind for p in pois)
    assert kinds[wb.KIND_PORT] == 2
    assert kinds[wb.KIND_TOWN] + kinds[wb.KIND_VILLAGE] + kinds[wb.KIND_PORT] == 6
    assert kinds[wb.KIND_MINE] == 2
    assert kinds[wb.KIND_RUIN] == 2
    assert kinds[wb.KIND_LIGHTHOUSE] == 1


def test_ids_unique_and_names_nonempty(world):
    pois = wb.place_pois(world, seed=7)
    ids = [p.id for p in pois]
    assert len(ids) == len(set(ids))
    assert all(p.name for p in pois)
    assert all(p.id.startswith(p.kind + "-") for p in pois)


def test_deterministic(world):
    a = [p.to_dict() for p in wb.place_pois(world, seed=7)]
    b = [p.to_dict() for p in wb.place_pois(world, seed=7)]
    assert a == b


def test_all_water_world_returns_empty():
    world = {"height": np.zeros((16, 16)), "water": np.full((16, 16), 3, np.uint8),
             "sea_level": 0.0}
    assert wb.place_pois(world) == []


def test_main_landmass_excludes_islet():
    water = np.zeros((20, 20), dtype=np.uint8)
    water[:, :3] = 3                      # 左侧一条海
    water[8:13, 15:20] = 3                # 右上一片海
    water[10, 17] = 0                     # 海里的一格孤岛
    main = P.main_landmass(water)
    assert main[10, 10], "大陆应被保留"
    assert not main[10, 17], "孤岛不该算主陆块"


def test_slope_field_flat_is_zero():
    assert np.allclose(P.slope_field(np.zeros((8, 8))), 0.0)


def test_prio_score_sorted(world):
    pois = wb.place_pois(world, seed=7)
    scores = [p.score for p in pois]
    assert scores == sorted(scores, reverse=True)
