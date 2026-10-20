"""worldbuilder —— 程序化生成库。

供各游戏项目 import 复用：

    import worldbuilder as wb
    hm = wb.generate_heightmap(64, 64, seed=1)
    d  = wb.generate_dungeon(48, 32, rooms=8, seed=2)
    names = wb.NameGenerator(style='fantasy').generate(10)
    drops = wb.LootTable([("金币",50,(1,10)),("传说剑",1,(1,1))]).roll(5)
"""
from __future__ import annotations

from .noise import (value_noise, perlin_noise, fractal_noise, fbm, simplex_noise,
                    warp_noise, ridged_noise, cellular_noise)
from .dungeon import (generate_dungeon, generate_dungeon_bsp, generate_cave,
                      to_ascii)
from .town import generate_town
from .namegen import NameGenerator
from .loot import LootTable
from .terrain import (generate_heightmap, classify, generate_terrain,
                      generate_moisture, classify_biomes, generate_world,
                      WATER, SAND, GRASS, FOREST, MOUNTAIN, TERRAIN_NAMES,
                      BIOME_NAMES)
from .road import (gobi_corridor, sample_height, smoothstep)
from .hydro import (fill_depressions, flow_directions, flow_accumulation,
                    extract_rivers, lakes, coastline, river_width, hydrology)
from .climate import (temperature_map, precipitation_map,
                      classify_biomes_climate, climate_maps, CLIMATE_BIOME_NAMES)
from .worldgen import (generate_world_full, describe,
                       WATER_NONE, WATER_RIVER, WATER_LAKE, WATER_SEA)

__all__ = [
    "value_noise", "perlin_noise", "fractal_noise", "fbm", "simplex_noise",
    "warp_noise", "ridged_noise", "cellular_noise",
    "generate_dungeon", "generate_dungeon_bsp", "generate_cave", "to_ascii",
    "generate_town",
    "NameGenerator",
    "LootTable",
    "generate_heightmap", "classify", "generate_terrain",
    "generate_moisture", "classify_biomes", "generate_world",
    "WATER", "SAND", "GRASS", "FOREST", "MOUNTAIN", "TERRAIN_NAMES",
    "BIOME_NAMES",
    "gobi_corridor", "sample_height", "smoothstep",
    # 水文（填洼 / 流向 / 汇水 / 河流 / 湖泊 / 海岸）
    "fill_depressions", "flow_directions", "flow_accumulation",
    "extract_rivers", "lakes", "coastline", "river_width", "hydrology",
    # 气候（温度 / 降水 / 生物群系）
    "temperature_map", "precipitation_map", "classify_biomes_climate",
    "climate_maps", "CLIMATE_BIOME_NAMES",
    # 世界编排
    "generate_world_full", "describe",
    "WATER_NONE", "WATER_RIVER", "WATER_LAKE", "WATER_SEA",
]
