"""世界编排：把各层按依赖顺序串起来，产出可直接交给渲染端/玩法层的一整套数据。

原库的问题是"层与层之间只有一条边"（高度 → 生物群系），水系与气候各自为政。
本模块把顺序钉死：

    高度图 → 海平面 → 填洼 → 流向 → 汇水 → 河流/湖泊/海岸 → 温度 → 降水 → 生物群系

每一步的产物都留在返回值里，便于下游只取自己需要的那层（渲染端要 height/water，
玩法端要 rivers/lakes，美术要 biomes）。**不引入任何新依赖，也不改老 API。**

随机性：所有子层共用同一个 ``seed``，但派生方式是显式错开的（高度用 seed，
噪声细节用 seed+偏移），因此同 seed 全流程可复现。
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .terrain import generate_heightmap
from .hydro import hydrology
from .climate import climate_maps

#: 水面编码（worldspec 草案里的 ``water`` 图层）
WATER_NONE, WATER_RIVER, WATER_LAKE, WATER_SEA = 0, 1, 2, 3


def _auto_sea_level(hm: np.ndarray, sea_fraction: float) -> float:
    """按"希望多少比例是水面"反推海平面。"""
    f = float(np.clip(sea_fraction, 0.0, 0.95))
    if f <= 0.0:
        return float(np.min(hm)) - 1e-6
    return float(np.quantile(hm, f))


def generate_world_full(width: int = 256, height: int = 256, seed: int = 0,
                        scale: float = 0.06, octaves: int = 5,
                        falloff: float = 0.0,
                        sea_level: Optional[float] = None,
                        sea_fraction: float = 0.35,
                        wind_from_deg: float = 270.0,
                        height_scale_m: float = 1200.0,
                        north_up: bool = True,
                        river_threshold: Optional[float] = None,
                        with_rivers: bool = True) -> dict:
    """生成一整个世界的全层数据。

    参数：
        width/height:   网格尺寸（行=height，列=width）
        falloff:        >0 时叠加径向衰减成岛屿（典型 0.2~0.5）
        sea_level:      指定海平面；``None`` 则由 ``sea_fraction`` 分位数反推
        sea_fraction:   目标水面占比（仅当 sea_level 为 None 时生效）
        wind_from_deg:  盛行风来向（气象学口径，270 = 西风）
        height_scale_m: 高度 1.0 折算多少米（影响温度递减与高山判定）
        river_threshold: 成河阈值（汇水格数）；缺省按格数自适应

    返回 dict：
        ``height``      原始高度图 float32 (h, w)
        ``filled``      填洼后高度 float32
        ``water``       uint8 水面类型（0 无 / 1 河 / 2 湖 / 3 海）
        ``sea_level``   float
        ``temperature`` float32 °C
        ``precipitation`` float32 0..1
        ``biomes``      int8（12 类，见 climate.CLIMATE_BIOME_NAMES）
        ``rivers``      折线列表 [{points, mouth, acc_max, length, width_max}]
        ``lakes``       湖泊信息 dict
        ``coast``       海岸掩码 bool
        ``acc``         汇水累积 float32
        ``meta``        {seed, size, sea_level, wind, sea_fraction, version}
    """
    if width < 16 or height < 16:
        raise ValueError(f"世界尺寸过小，至少 16x16，收到 {width}x{height}")
    seed = int(seed)

    hm = generate_heightmap(width, height, seed=seed, scale=scale,
                            octaves=octaves, falloff=falloff)
    sea = (_auto_sea_level(hm, sea_fraction) if sea_level is None
           else float(sea_level))

    hy = hydrology(hm, sea_level=sea, river_threshold=river_threshold,
                   with_rivers=with_rivers)
    cl = climate_maps(hm, wind_from_deg=wind_from_deg, sea_level=sea,
                      height_scale_m=height_scale_m, north_up=north_up)

    # 水面类型：海优先，其次湖，再河
    water = np.zeros(hm.shape, dtype=np.uint8)
    water[hy["river_mask"]] = WATER_RIVER
    lake_mask = hy["lakes"]["mask"]
    water[lake_mask] = WATER_LAKE
    water[hm <= sea] = WATER_SEA

    return {
        "height": hm.astype(np.float32),
        "filled": hy["filled"],
        "water": water,
        "sea_level": float(sea),
        "temperature": cl["temperature"],
        "precipitation": cl["precipitation"],
        "biomes": cl["biomes"],
        "rivers": hy["rivers"],
        "lakes": hy["lakes"],
        "coast": hy["coast"],
        "acc": hy["acc"],
        "meta": {
            "seed": seed,
            "size": (int(height), int(width)),
            "sea_level": float(sea),
            "sea_fraction": None if sea_level is not None else float(sea_fraction),
            "wind": cl["wind"],
            "height_scale_m": float(height_scale_m),
            "river_threshold": hy["river_threshold"],
            "version": "worldbuilder/world-full/1",
        },
    }


def describe(world: dict) -> str:
    """一眼看清这个世界长什么样（CLI/日志用，不依赖 matplotlib）。"""
    b = world["biomes"]
    total = b.size
    lines = [
        f"尺寸 {world['meta']['size'][0]}x{world['meta']['size'][1]}"
        f" | seed={world['meta']['seed']} | 海平面={world['sea_level']:.3f}",
        f"河流 {len(world['rivers'])} 条 | 湖泊 {world['lakes']['count']} 个"
        f" | 海岸格 {int(world['coast'].sum())}",
    ]
    from .climate import CLIMATE_BIOME_NAMES
    shares = [(code, int((b == code).sum())) for code in CLIMATE_BIOME_NAMES]
    shares.sort(key=lambda x: -x[1])
    parts = [f"{CLIMATE_BIOME_NAMES[code]} {n * 100.0 / total:.1f}%"
             for code, n in shares if n > 0]
    lines.append("群系：" + "、".join(parts))
    return "\n".join(lines)
