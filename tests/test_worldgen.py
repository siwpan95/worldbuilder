"""世界编排测试：层级齐全、水面比例、可复现、老接口不回归、分辨率无关的河数。
"""

import time

import numpy as np

from worldbuilder import (
    generate_world_full, describe, generate_world,
    WATER_SEA, WATER_RIVER, WATER_LAKE,
    CLIMATE_BIOME_NAMES,
)


def _world(seed=7, n=96, **kw):
    return generate_world_full(n, n, seed=seed, falloff=0.35, **kw)


def test_all_layers_present_and_shaped():
    w = _world()
    n = 96
    for key in ("height", "filled", "water", "temperature", "precipitation",
                "biomes", "rivers", "lakes", "coast", "acc"):
        assert key in w, f"缺少图层 {key}"
    for key in ("height", "filled", "water", "temperature", "precipitation",
                "biomes", "coast", "acc"):
        assert w[key].shape == (n, n), f"{key} 形状不对: {w[key].shape}"
    assert w["height"].dtype == np.float32
    assert w["water"].dtype == np.uint8
    assert w["biomes"].dtype == np.int8


def test_meta_snapshot():
    w = _world()
    m = w["meta"]
    assert m["seed"] == 7
    assert m["size"] == (96, 96)
    assert m["version"].startswith("worldbuilder/world-full/")
    assert m["wind"]["code"] in ("N", "E", "S", "W")
    assert 0.0 < m["sea_level"] < 1.0


def test_sea_fraction_close_to_request():
    for frac in (0.20, 0.35, 0.55):
        w = generate_world_full(128, 128, seed=3, falloff=0.2, sea_fraction=frac)
        actual = float((w["water"] == WATER_SEA).mean())
        assert abs(actual - frac) < 0.02, f"目标 {frac} 实际 {actual:.3f}"


def test_water_layer_priority():
    """海 > 湖 > 河：同一格同时命中时取优先级高的。"""
    w = _world()
    sea = w["water"] == WATER_SEA
    river = w["water"] == WATER_RIVER
    lake = w["water"] == WATER_LAKE
    assert not np.any(sea & (river | lake))
    assert w["height"][sea].max() <= w["sea_level"] + 1e-6
    assert np.any(river), "应有河格"
    assert np.any(lake), "应有湖格"


def test_deterministic_per_seed():
    a = _world(seed=11)
    b = _world(seed=11)
    assert np.array_equal(a["water"], b["water"])
    assert np.array_equal(a["height"], b["height"])
    assert len(a["rivers"]) == len(b["rivers"])
    for ra, rb in zip(a["rivers"], b["rivers"]):
        assert ra["points"] == rb["points"]


def test_different_seed_differs():
    a = _world(seed=1)
    b = _world(seed=2)
    assert not np.array_equal(a["height"], b["height"])


def test_rivers_are_polylines_with_flow():
    w = _world()
    assert len(w["rivers"]) >= 5, "96² 岛上应有若干条河"
    for rv in w["rivers"]:
        pts = rv["points"]
        assert len(pts) >= 4
        for x, y in pts:
            assert 0 <= x < 96 and 0 <= y < 96
        assert rv["acc_max"] >= w["meta"]["river_threshold"]


def test_river_count_stable_across_resolution():
    """同一 seed、不同分辨率：主干河数不应随格数线性膨胀（阈值按格数/80 归一）。"""
    counts = {n: len(generate_world_full(n, n, seed=21, falloff=0.35)["rivers"])
              for n in (96, 192)}
    assert abs(counts[96] - counts[192]) <= max(12, counts[96]), (
        f"河数随分辨率漂移过大: {counts}"
    )


def test_biomes_only_known_codes():
    w = _world()
    codes = set(np.unique(w["biomes"]).tolist())
    assert codes.issubset(set(CLIMATE_BIOME_NAMES)), f"出现未知群系码 {codes}"
    assert len(codes) >= 4, "一个岛至少该有 4 种群系"


def test_describe_output():
    text = describe(_world())
    assert "河流" in text and "湖泊" in text
    assert "群系：" in text
    assert "seed=7" in text


def test_legacy_generate_world_untouched():
    old = generate_world(48, 48, seed=5)
    assert set(old) == {"heightmap", "moisture", "temperature", "biomes"}
    assert old["heightmap"].shape == (48, 48)
    assert old["biomes"].dtype == np.int8
    assert set(np.unique(old["biomes"]).tolist()) <= set(range(8)), "老接口仍是 8 类编码"


def test_small_world_rejected():
    for n in (8, 15):
        try:
            generate_world_full(n, n)
        except ValueError:
            continue
        raise AssertionError(f"{n}x{n} 应被拒绝")


def test_performance_budget_256():
    """256² 全链路应在一秒级完成（纯 numpy；超时说明某层退化成了 Python 循环）。"""
    t = time.perf_counter()
    generate_world_full(256, 256, seed=1)
    dt = time.perf_counter() - t
    assert dt < 5.0, f"256² 耗时 {dt:.1f}s，超出预算"
