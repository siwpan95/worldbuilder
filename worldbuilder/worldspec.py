"""worldspec v1：三仓之间唯一的"共享物"是**文件格式**，不是代码依赖。

背景：worldbuilder / 3dworld / an-engine 各自独立发版（守"复制优于共享"），
所以协同只能靠数据契约。本模块把 ``generate_world_full()`` 的产物落成一套
自描述目录，渲染端与玩法端各自读自己需要的那几层。

目录结构（``out_dir`` 下）::

    meta.json          清单：spec 版本、尺寸、海平面、坐标约定、seed、生成器版本
    height.f32.npy     原始高度图 float32（行主序，[0,1]）
    filled.f32.npy     填洼后高度（水文用）
    biome.u8.npy       12 类群系编码 uint8
    water.u8.npy       0 无 / 1 河 / 2 湖 / 3 海
    temperature.f32.npy
    precip.f32.npy     相对降水指数 [0,1]
    rivers.geojson     河流折线（LineString，坐标为网格单位）
    lakes.json         湖泊摘要（面积、包围盒、水面高程）
    pois.json          兴趣点（GeoJSON Point：城镇/港口/矿/遗迹）——可选
    graph.json         路网（nodes + edges，边带折线）——可选

坐标约定（写死在 meta 里，消费方按它解释数组）：
- 右手系、**Y 向上**、X 向东、Z 向南；
- ``height[r][c]`` 的 ``r`` 对应 +z，``c`` 对应 +x，与 3dworld
  ``geometry.heightfield`` / ``engine.terrain_lod`` 的行主序一致；
- 世界单位是米，``tile_m`` 给出一格代表多少米（默认 1.0）。

版本策略：``meta["spec"]`` 必须严格等于 ``worldspec/1``；不匹配直接拒读，
不做"猜字段"式兼容。新增可选图层只加文件名，不改已有字段语义。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np

SPEC_NAME = "worldspec/1"

#: 必需图层：缺失即视为损坏
REQUIRED_LAYERS = ("height", "biome", "water")

#: 图层文件名表（逻辑名 -> 文件名 + dtype）
_LAYERS = {
    "height": ("height.f32.npy", np.float32),
    "filled": ("filled.f32.npy", np.float32),
    "biome": ("biome.u8.npy", np.uint8),
    "water": ("water.u8.npy", np.uint8),
    "temperature": ("temperature.f32.npy", np.float32),
    "precip": ("precip.f32.npy", np.float32),
}


#: 可选 JSON 图层（不是数组，单独处理）
_JSON_LAYERS = {"pois": "pois.json", "graph": "graph.json"}


class WorldSpecError(ValueError):
    """worldspec 目录不合法（版本不匹配、缺图层、尺寸不一致）。"""


def _meta_of(world: dict, *, tile_m: float, generator: str) -> dict:
    h = np.asarray(world["height"])
    rivers = world.get("rivers") or []
    roads = world.get("roads") or {}
    return {
        "spec": SPEC_NAME,
        "generator": generator,
        "seed": (world.get("meta") or {}).get("seed"),
        "size": [int(h.shape[0]), int(h.shape[1])],
        "tile_m": float(tile_m),
        "up_axis": "Y",
        "handedness": "right",
        "sea_level": float(world.get("sea_level", 0.0)),
        "height_scale_m": float((world.get("meta") or {}).get("height_scale_m", 1000.0)),
        "wind": (world.get("meta") or {}).get("wind"),
        "layers": {name: fn for name, (fn, _dt) in _LAYERS.items()
                   if world.get(_key_of(name)) is not None},
        "rivers": {"count": len(rivers), "file": "rivers.geojson",
                   "units": "grid", "coord": "x,z"},
        "lakes": {"count": int((world.get("lakes") or {}).get("count", 0)),
                  "file": "lakes.json"},
        **({"pois": {"count": len(world.get("pois") or []),
                     "file": "pois.json", "units": "grid", "coord": "x,z"}}
           if world.get("pois") else {}),
        **({"graph": {"nodes": len(roads.get("nodes") or []),
                      "edges": len(roads.get("edges") or []),
                      "file": "graph.json", "units": "grid", "coord": "x,z"}}
           if roads else {}),
    }


def _as_dict(obj) -> dict:
    """``Poi`` 或 dict 统一成 dict（``Poi`` 有 ``to_dict``）。"""
    return obj.to_dict() if hasattr(obj, "to_dict") else dict(obj)


def _key_of(layer: str) -> str:
    """图层逻辑名 -> ``generate_world_full`` 返回值的键名（读回时也用同一套键）。"""
    return {"precip": "precipitation", "biome": "biomes"}.get(layer, layer)


def _rivers_geojson(rivers: Iterable[dict]) -> dict:
    feats = []
    for rv in rivers:
        pts = [[float(x), float(y)] for x, y in rv.get("points", [])]
        if len(pts) < 2:
            continue
        feats.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": pts},
            "properties": {
                "acc_max": float(rv.get("acc_max", 0.0)),
                "length": float(rv.get("length", len(pts) - 1)),
                "width_max": float(rv.get("width_max", 0.0)),
            },
        })
    return {"type": "FeatureCollection", "features": feats}


def save_world(world: dict, out_dir, *, tile_m: float = 1.0,
               generator: str = "worldbuilder") -> dict:
    """把 ``generate_world_full`` 的产物写成 worldspec 目录，返回 manifest。

    已存在的同名文件会被覆盖（同 seed 重跑不残留旧图层）。
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    missing = [k for k in ("height", "biomes", "water") if k not in world]
    if missing:
        raise WorldSpecError(f"world 缺少必需图层 {missing}；请用 generate_world_full() 的产物")

    arrays = {
        "height": world["height"],
        "filled": world.get("filled"),
        "biome": world["biomes"],
        "water": world["water"],
        "temperature": world.get("temperature"),
        "precip": world.get("precipitation"),
    }
    shape = np.asarray(arrays["height"]).shape
    for name, arr in arrays.items():
        if arr is None:
            continue
        a = np.asarray(arr)
        if a.shape != shape:
            raise WorldSpecError(f"图层 {name} 形状 {a.shape} 与高度图 {shape} 不一致")
        fn, dt = _LAYERS[name]
        np.save(out / fn, a.astype(dt, copy=False))

    (out / "rivers.geojson").write_text(
        json.dumps(_rivers_geojson(world.get("rivers") or []), ensure_ascii=False),
        encoding="utf-8")

    lakes = world.get("lakes") or {}
    lake_rows = [{"area": int(lk["area"]), "bbox": list(lk["bbox"]),
                  "surface": float(lk["surface"])}
                 for lk in (lakes.get("lakes") or [])]
    (out / "lakes.json").write_text(
        json.dumps({"count": len(lake_rows), "lakes": lake_rows}, ensure_ascii=False),
        encoding="utf-8")

    pois = world.get("pois") or []
    if pois:
        feats = []
        for p in pois:
            d = _as_dict(p)
            feats.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(d["x"]), float(d["z"])]},
                "properties": {"id": d["id"], "kind": d["kind"], "name": d.get("name", ""),
                               "score": float(d.get("score", 0.0)),
                               "meta": d.get("meta") or {}},
            })
        (out / "pois.json").write_text(
            json.dumps({"type": "FeatureCollection", "spec": SPEC_NAME,
                        "features": feats}, ensure_ascii=False), encoding="utf-8")

    roads = world.get("roads") or {}
    if roads.get("edges") is not None:
        nodes = [_as_dict(n) for n in (roads.get("nodes") or [])]
        edges = []
        for e in roads.get("edges") or []:
            edges.append({
                "a": e["a"], "b": e["b"], "kind": e.get("kind", "trunk"),
                "length": float(e.get("length", 0.0)),
                "straight": float(e.get("straight", 0.0)),
                "cost": float(e.get("cost", 0.0)),
                "points": [[float(x), float(z)] for x, z in e.get("points") or []],
            })
        (out / "graph.json").write_text(
            json.dumps({"spec": SPEC_NAME, "nodes": nodes, "edges": edges},
                       ensure_ascii=False), encoding="utf-8")

    meta = _meta_of(world, tile_m=tile_m, generator=generator)
    (out / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def read_meta(spec_dir) -> dict:
    """只读清单（消费方通常先读它，再决定要加载哪几个 npy）。"""
    p = Path(spec_dir) / "meta.json"
    if not p.exists():
        raise WorldSpecError(f"{p} 不存在：这不是一个 worldspec 目录")
    meta = json.loads(p.read_text(encoding="utf-8"))
    if meta.get("spec") != SPEC_NAME:
        raise WorldSpecError(
            f"spec 版本不匹配：期望 {SPEC_NAME}，收到 {meta.get('spec')!r}"
        )
    for key in ("size", "tile_m", "up_axis"):
        if key not in meta:
            raise WorldSpecError(f"meta.json 缺少字段 {key!r}")
    return meta


def load_world(spec_dir, *, layers: Optional[Iterable[str]] = None) -> dict:
    """读回 worldspec 目录。

    ``layers`` 可只取需要的层（例如渲染端只要 ``height/water``），省内存。
    缺失的可选层返回 ``None``；缺必需层则抛 ``WorldSpecError``。
    """
    out_dir = Path(spec_dir)
    meta = read_meta(out_dir)
    want = set(layers) if layers is not None else set(_LAYERS)

    data: Dict[str, object] = {"meta": meta, "spec": meta["spec"]}
    for name, (fn, _dt) in _LAYERS.items():
        if name not in want:
            continue
        p = out_dir / fn
        if not p.exists():
            if name in REQUIRED_LAYERS:
                raise WorldSpecError(f"缺少必需图层 {name}（{fn}）")
            data[_key_of(name)] = None
            continue
        arr = np.load(p)
        if list(arr.shape) != list(meta["size"]):
            raise WorldSpecError(
                f"图层 {name} 形状 {arr.shape} 与 meta.size {meta['size']} 不一致"
            )
        data[_key_of(name)] = arr

    if (layers is None or "pois" in want) and (out_dir / "pois.json").exists():
        geo = json.loads((out_dir / "pois.json").read_text(encoding="utf-8"))
        data["pois"] = [
            {"id": f["properties"]["id"], "kind": f["properties"]["kind"],
             "name": f["properties"].get("name", ""),
             "score": f["properties"].get("score", 0.0),
             "x": float(f["geometry"]["coordinates"][0]),
             "z": float(f["geometry"]["coordinates"][1]),
             "meta": f["properties"].get("meta") or {}}
            for f in geo.get("features", [])
        ]
    if (layers is None or "graph" in want) and (out_dir / "graph.json").exists():
        g = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
        data["graph"] = {"nodes": g.get("nodes", []), "edges": g.get("edges", [])}

    geo_p = out_dir / "rivers.geojson"
    if geo_p.exists() and (layers is None or "rivers" in want):
        geo = json.loads(geo_p.read_text(encoding="utf-8"))
        data["rivers"] = [
            {"points": [(c[0], c[1]) for c in f["geometry"]["coordinates"]],
             "acc_max": f["properties"].get("acc_max", 0.0),
             "length": f["properties"].get("length", 0.0),
             "width_max": f["properties"].get("width_max", 0.0)}
            for f in geo.get("features", [])
        ]
    return data


def validate(spec_dir) -> List[str]:
    """体检：返回问题清单（空列表 = 通过）。不抛异常，便于 CLI/CI 汇总。"""
    problems: List[str] = []
    out = Path(spec_dir)
    try:
        meta = read_meta(out)
    except WorldSpecError as exc:
        return [str(exc)]

    size = meta["size"]
    for name, (fn, _dt) in _LAYERS.items():
        p = out / fn
        if not p.exists():
            if name in REQUIRED_LAYERS:
                problems.append(f"缺必需图层 {name}（{fn}）")
            continue
        arr = np.load(p)
        if list(arr.shape) != list(size):
            problems.append(f"{fn} 形状 {list(arr.shape)} != size {size}")

    water_p = out / "water.u8.npy"
    if water_p.exists():
        vals = set(np.unique(np.load(water_p)).tolist())
        extra = vals - {0, 1, 2, 3}
        if extra:
            problems.append(f"water 出现未定义编码 {sorted(extra)}")

    geo_p = out / "rivers.geojson"
    if geo_p.exists():
        try:
            geo = json.loads(geo_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"rivers.geojson 不是合法 JSON: {exc}")
        else:
            if geo.get("type") != "FeatureCollection":
                problems.append("rivers.geojson 顶层 type 应为 FeatureCollection")
            for i, f in enumerate(geo.get("features", [])):
                if f.get("geometry", {}).get("type") != "LineString":
                    problems.append(f"rivers.features[{i}] 不是 LineString")
                elif len(f["geometry"].get("coordinates", [])) < 2:
                    problems.append(f"rivers.features[{i}] 少于 2 个点")
    size_h, size_w = int(size[0]), int(size[1])

    def _in_bounds(x: float, z: float) -> bool:
        return -0.5 <= x <= size_w - 0.5 and -0.5 <= z <= size_h - 0.5

    pois_p = out / "pois.json"
    if pois_p.exists():
        try:
            geo = json.loads(pois_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"pois.json 不是合法 JSON: {exc}")
        else:
            if geo.get("type") != "FeatureCollection":
                problems.append("pois.json 顶层 type 应为 FeatureCollection")
            for i, f in enumerate(geo.get("features", [])):
                geom = f.get("geometry") or {}
                if geom.get("type") != "Point":
                    problems.append(f"pois.features[{i}] 不是 Point")
                    continue
                x, z = geom.get("coordinates", [0, 0])[:2]
                if not _in_bounds(float(x), float(z)):
                    problems.append(f"pois.features[{i}] 坐标 ({x},{z}) 越界 {size}")
                if not (f.get("properties") or {}).get("id"):
                    problems.append(f"pois.features[{i}] 缺 id")

    graph_p = out / "graph.json"
    if graph_p.exists():
        try:
            g = json.loads(graph_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"graph.json 不是合法 JSON: {exc}")
        else:
            ids = {n.get("id") for n in g.get("nodes", [])}
            for i, e in enumerate(g.get("edges", [])):
                if e.get("a") not in ids:
                    problems.append(f"graph.edges[{i}] 指向未知节点 {e.get('a')!r}")
                if e.get("b") not in ids:
                    problems.append(f"graph.edges[{i}] 指向未知节点 {e.get('b')!r}")
                pts = e.get("points") or []
                if len(pts) < 2:
                    problems.append(f"graph.edges[{i}] 折线少于 2 点")
                for x, z in pts:
                    if not _in_bounds(float(x), float(z)):
                        problems.append(f"graph.edges[{i}] 折线点 ({x},{z}) 越界")
                        break
    return problems
