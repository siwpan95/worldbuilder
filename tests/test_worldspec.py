"""worldspec v1 测试：往返一致、版本拒读、缺层策略、体检能查出坏数据。

worldspec 是三个仓之间**唯一**的耦合面（格式，不是代码），所以这里钉的是
"消费方能不能放心读"：几何/坐标约定写死在 meta 里、数组必须与 size 对齐、
可选层缺失要能降级、坏数据要能报出来而不是读到一半炸。
"""

import json

import numpy as np
import pytest

import worldbuilder as wb
from worldbuilder.worldspec import SPEC_NAME, WorldSpecError


@pytest.fixture(scope="module")
def world():
    return wb.generate_world_full(64, 64, seed=5, falloff=0.3)


def test_save_creates_expected_files(tmp_path, world):
    meta = wb.save_world(world, tmp_path, tile_m=4.0)
    names = {p.name for p in tmp_path.iterdir()}
    for fn in ("meta.json", "height.f32.npy", "filled.f32.npy", "biome.u8.npy",
               "water.u8.npy", "temperature.f32.npy", "precip.f32.npy",
               "rivers.geojson", "lakes.json"):
        assert fn in names, f"缺少 {fn}"
    assert meta["spec"] == SPEC_NAME
    assert meta["size"] == [64, 64]
    assert meta["tile_m"] == 4.0
    assert meta["up_axis"] == "Y" and meta["handedness"] == "right"


def test_roundtrip_bit_equal(tmp_path, world):
    wb.save_world(world, tmp_path)
    back = wb.load_world(tmp_path)
    for key in ("height", "filled", "biomes", "water", "temperature", "precipitation"):
        assert np.array_equal(back[key], np.asarray(world[key])), f"{key} 往返不一致"
        assert back[key].dtype == np.asarray(world[key]).astype(back[key].dtype).dtype
    assert back["meta"]["seed"] == 5
    assert back["meta"]["spec"] == SPEC_NAME


def test_roundtrip_preserves_river_geometry(tmp_path, world):
    wb.save_world(world, tmp_path)
    back = wb.load_world(tmp_path)
    assert len(back["rivers"]) == len(world["rivers"])
    for a, b in zip(world["rivers"], back["rivers"]):
        assert [(float(x), float(y)) for x, y in a["points"]] == \
               [(float(x), float(y)) for x, y in b["points"]]


def test_load_subset_of_layers(tmp_path, world):
    wb.save_world(world, tmp_path)
    only = wb.load_world(tmp_path, layers=("height", "water"))
    assert set(only) >= {"height", "water", "meta", "spec"}
    assert "biomes" not in only and "temperature" not in only
    assert only["height"].shape == (64, 64)


def test_read_meta_only(tmp_path, world):
    wb.save_world(world, tmp_path)
    meta = wb.read_meta(tmp_path)
    assert meta["layers"]["height"] == "height.f32.npy"
    assert meta["rivers"]["count"] == len(world["rivers"])
    assert meta["lakes"]["count"] == world["lakes"]["count"]


def test_spec_version_mismatch_rejected(tmp_path, world):
    wb.save_world(world, tmp_path)
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    meta["spec"] = "worldspec/2"
    (tmp_path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(WorldSpecError, match="spec 版本不匹配"):
        wb.read_meta(tmp_path)


def test_missing_required_layer_rejected(tmp_path, world):
    wb.save_world(world, tmp_path)
    (tmp_path / "water.u8.npy").unlink()
    with pytest.raises(WorldSpecError, match="缺少必需图层 water"):
        wb.load_world(tmp_path)


def test_missing_optional_layer_returns_none(tmp_path, world):
    wb.save_world(world, tmp_path)
    (tmp_path / "precip.f32.npy").unlink()
    back = wb.load_world(tmp_path)
    assert back["precipitation"] is None


def test_shape_mismatch_rejected(tmp_path, world):
    wb.save_world(world, tmp_path)
    np.save(tmp_path / "height.f32.npy", np.zeros((32, 32), dtype=np.float32))
    with pytest.raises(WorldSpecError, match="不一致"):
        wb.load_world(tmp_path)


def test_validate_ok_and_detects_problems(tmp_path, world):
    wb.save_world(world, tmp_path)
    assert wb.validate(tmp_path) == []

    water = np.load(tmp_path / "water.u8.npy")
    water[0, 0] = 9
    np.save(tmp_path / "water.u8.npy", water)
    problems = wb.validate(tmp_path)
    assert any("未定义编码" in p for p in problems)

    (tmp_path / "rivers.geojson").write_text("{not json", encoding="utf-8")
    assert any("不是合法 JSON" in p for p in wb.validate(tmp_path))


def test_validate_reports_bad_geometry(tmp_path, world):
    wb.save_world(world, tmp_path)
    geo = json.loads((tmp_path / "rivers.geojson").read_text(encoding="utf-8"))
    geo["features"][0]["geometry"] = {"type": "Point", "coordinates": [1, 2]}
    (tmp_path / "rivers.geojson").write_text(json.dumps(geo), encoding="utf-8")
    assert any("不是 LineString" in p for p in wb.validate(tmp_path))


def test_save_overwrites_stale_layers(tmp_path, world):
    """同目录重跑不能残留上一版的图层（否则消费方读到旧数据）。"""
    wb.save_world(world, tmp_path)
    small = wb.generate_world_full(32, 32, seed=9)
    wb.save_world(small, tmp_path)
    meta = wb.read_meta(tmp_path)
    assert meta["size"] == [32, 32]
    assert np.load(tmp_path / "height.f32.npy").shape == (32, 32)


def test_missing_world_keys_rejected(tmp_path):
    with pytest.raises(WorldSpecError, match="缺少必需图层"):
        wb.save_world({"height": np.zeros((8, 8), dtype=np.float32)}, tmp_path)


def test_not_a_spec_dir(tmp_path):
    with pytest.raises(WorldSpecError, match="不是一个 worldspec 目录"):
        wb.read_meta(tmp_path)
