# -*- coding: utf-8 -*-
"""worldbuilder 的 bridge 友好接口（**新增文件，不改既有模块**）。

给「超级引擎」组合仓（superengine）用的稳定入口：把本仓的世界生成能力按
**契约形状**暴露出来，避免组合仓直接 import 内部模块（那会让组合仓依赖本仓的内部结构，
本仓一重构就断）。

设计约定
--------
* 本文件是**纯适配层**：不含算法，只转发到 `worldgen` / `worldspec`；
* `SUPPORTED_CONTRACTS` 声明本仓能满足哪些契约及**兼容区间**（版本由组合仓的契约独立管理）；
* 保持本仓既有纪律：**纯 numpy、无 GL、无第三方依赖**。

坐标约定（与 worldspec v1 一致）：右手系、Y 上；``height[r][c]`` 的 ``r → +z``、``c → +x``；
``tile_m`` 为每格米数。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional

import numpy as np

from .worldgen import generate_world_complete, generate_world_full
from .worldspec import load_world, read_meta, save_world, validate

__all__ = [
    "BRIDGE_VERSION",
    "SUPPORTED_CONTRACTS",
    "generate",
    "generate_complete",
    "save",
    "load",
    "validate_spec",
    "meta",
    "heightfield",
    "make_height_sampler",
    "tile_m_of",
]

#: 本 bridge 接口自身的版本（与契约版本是两套号，别混）
BRIDGE_VERSION = "1.0.0"

#: 本仓声明能满足的契约及兼容区间 —— 由组合仓在装配期校验
SUPPORTED_CONTRACTS = {
    "worldspec_source": ">=1.0,<2.0",
    "terrain_source": ">=1.0,<2.0",
}

REQUIRED_LAYERS = ("height", "biome", "water")


# ------------------------------------------------------------ 生成 / 存取 --
def generate(width: int = 256, height: int = 256, seed: int = 0, **kw) -> dict:
    """生成世界（转发 `worldgen.generate_world_full`），返回含 `height/biomes/water` 的 dict。"""
    return generate_world_full(width=width, height=height, seed=seed, **kw)


def generate_complete(width: int = 256, height: int = 256, seed: int = 0, **kw) -> dict:
    """生成**完整**世界：在 `generate` 之上再串 POI 选址与路网（`worldgen.generate_world_complete`）。

    产出含 ``pois`` / ``graph`` —— 落盘后就是 worldspec 的 `pois.json` / `graph.json`，
    玩法侧（an-engine `MapGraph.from_worldspec`）靠它才有节点可寻路。
    只做地形时用 `generate` 更快；要跑通「生成 → 玩法」整条链用这个。
    """
    return generate_world_complete(width=width, height=height, seed=seed, **kw)


def save(world: dict, out_dir, *, tile_m: float = 1.0,
         generator: str = "worldbuilder") -> dict:
    """写成 worldspec v1 目录，返回 manifest。"""
    return save_world(world, out_dir, tile_m=tile_m, generator=generator)


def load(spec_dir, *, layers: Optional[Iterable[str]] = None) -> dict:
    """读 worldspec v1 目录 → {层名: ndarray}（可选只取部分层）。"""
    return load_world(spec_dir, layers=layers)


def validate_spec(spec_dir) -> List[str]:
    """校验 worldspec 目录；返回错误列表（空 = 通过）。"""
    return validate(spec_dir)


def meta(spec_dir) -> dict:
    """读 worldspec 的 meta.json。"""
    return read_meta(spec_dir)


def tile_m_of(spec_dir) -> float:
    """从 meta 取每格米数（缺失则按契约默认 1.0）。"""
    try:
        m = read_meta(spec_dir) or {}
    except Exception:                                       # noqa: BLE001
        return 1.0
    return float(m.get("tile_m", 1.0))


# -------------------------------------------------------------- 高程 ----
def heightfield(source: Any) -> np.ndarray:
    """从「world dict」或「worldspec 目录」取出高程阵列 ``(rows, cols)`` float。"""
    if isinstance(source, dict):
        arr = source.get("height")
        if arr is None:
            raise KeyError("world dict 里没有 'height' 层")
        return np.asarray(arr, dtype=float)
    layers = load_world(source, layers=["height"])
    return np.asarray(layers["height"], dtype=float)


def make_height_sampler(hm: np.ndarray, tile_m: float = 1.0,
                        height_scale: float = 1.0) -> Callable[[float, float], float]:
    """把高程阵列包成 ``f(world_x, world_z) -> height`` 的采样器。

    这是喂给表现层（3dworld clipmap / CDLOD 的 ``HeightFn``）的形状。
    双线性插值 + 边界钳制，**确定性**（同输入同输出，可进断言）。
    """
    hm = np.asarray(hm, dtype=float)
    rows, cols = hm.shape
    step = float(tile_m) if tile_m else 1.0

    def sample(x: float, z: float) -> float:
        fc = x / step
        fr = z / step
        c0 = int(np.floor(fc))
        r0 = int(np.floor(fr))
        tc = fc - c0
        tr = fr - r0
        c0 = min(max(c0, 0), cols - 1)
        r0 = min(max(r0, 0), rows - 1)
        c1 = min(c0 + 1, cols - 1)
        r1 = min(r0 + 1, rows - 1)
        v00 = hm[r0, c0]
        v10 = hm[r0, c1]
        v01 = hm[r1, c0]
        v11 = hm[r1, c1]
        v0 = v00 + (v10 - v00) * tc
        v1 = v01 + (v11 - v01) * tc
        return float((v0 + (v1 - v0) * tr) * height_scale)

    return sample
