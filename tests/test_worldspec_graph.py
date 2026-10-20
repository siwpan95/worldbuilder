"""worldspec 的 POI / 路网图层：往返保真 + 体检能抓坏数据。

这两个图层是 P1 之后 an-engine 的输入（`MapGraph.from_worldspec`），
一旦坐标或边引用写坏，下游会在寻路时莫名其妙地失败，所以这里把它们钉死。
"""

import json

import numpy as np
import pytest

import worldbuilder as wb


@pytest.fixture(scope="module")
def built():
    w = wb.generate_world_complete(64, 64, seed=5, falloff=0.3)
    return w


def test_meta_declares_pois_and_graph(tmp_path, built):
    meta = wb.save_world(built, tmp_path, tile_m=3.0)
    assert meta["pois"]["count"] == len(built["pois"])
    assert meta["pois"]["file"] == "pois.json"
    assert meta["graph"]["nodes"] == len(built["roads"]["nodes"])
    assert meta["graph"]["edges"] == len(built["roads"]["edges"])
    assert (tmp_path / "pois.json").exists()
    assert (tmp_path / "graph.json").exists()


def test_poi_roundtrip(tmp_path, built):
    wb.save_world(built, tmp_path)
    back = wb.load_world(tmp_path, layers=("height", "pois"))
    assert len(back["pois"]) == len(built["pois"])
    src = {p.id: p for p in built["pois"]}
    for row in back["pois"]:
        p = src[row["id"]]
        assert row["kind"] == p.kind
        assert row["x"] == float(p.x) and row["z"] == float(p.z)
        assert row["name"] == p.name


def test_graph_roundtrip(tmp_path, built):
    wb.save_world(built, tmp_path)
    back = wb.load_world(tmp_path, layers=("height", "graph"))
    g = back["graph"]
    assert len(g["nodes"]) == len(built["roads"]["nodes"])
    assert len(g["edges"]) == len(built["roads"]["edges"])
    e0 = g["edges"][0]
    assert {"a", "b", "kind", "length", "points"} <= set(e0)
    assert len(e0["points"]) >= 2


def test_validate_clean(tmp_path, built):
    wb.save_world(built, tmp_path)
    assert wb.validate(tmp_path) == []


def test_validate_detects_dangling_edge(tmp_path, built):
    wb.save_world(built, tmp_path)
    p = tmp_path / "graph.json"
    g = json.loads(p.read_text(encoding="utf-8"))
    g["edges"][0]["b"] = "ghost-99"
    p.write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
    problems = wb.validate(tmp_path)
    assert any("ghost-99" in s for s in problems), problems


def test_validate_detects_out_of_bounds_poi(tmp_path, built):
    wb.save_world(built, tmp_path)
    p = tmp_path / "pois.json"
    geo = json.loads(p.read_text(encoding="utf-8"))
    geo["features"][0]["geometry"]["coordinates"] = [9999.0, 0.0]
    p.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    problems = wb.validate(tmp_path)
    assert any("越界" in s for s in problems), problems


def test_validate_detects_degenerate_edge(tmp_path, built):
    wb.save_world(built, tmp_path)
    p = tmp_path / "graph.json"
    g = json.loads(p.read_text(encoding="utf-8"))
    g["edges"][0]["points"] = g["edges"][0]["points"][:1]
    p.write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
    problems = wb.validate(tmp_path)
    assert any("少于 2 点" in s for s in problems), problems


def test_world_without_pois_omits_files(tmp_path):
    w = wb.generate_world_full(48, 48, seed=2)
    meta = wb.save_world(w, tmp_path)
    assert "pois" not in meta and "graph" not in meta
    assert not (tmp_path / "pois.json").exists()
    assert not (tmp_path / "graph.json").exists()
