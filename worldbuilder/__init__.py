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
from .namegen import NameGenerator, GrammarGenerator, grammar_names
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
                       generate_world_complete, describe_complete,
                       WATER_NONE, WATER_RIVER, WATER_LAKE, WATER_SEA)
from .worldspec import (save_world, load_world, read_meta, validate,
                        WorldSpecError, SPEC_NAME)
from .poi import (Poi, place_pois, describe as describe_pois, slope_field,
                  poisson_disk_sample, place_pois_uniform,
                  KIND_TOWN, KIND_VILLAGE, KIND_PORT, KIND_MINE, KIND_RUIN,
                  KIND_LIGHTHOUSE, KIND_BRIDGE, KIND_FORD, SETTLEMENT_KINDS)
from .roadnet import (build_road_network, least_cost_path, road_cost_field,
                      describe_network)
from .wfc import (Tile, TileSet, wang_tileset, generate_wfc, rasterize,
                  generate_wfc_overlapping, generate_dungeon_wfc, WfcContradiction)
from .dungeongraph import (Room, build_dungeon_graph, detect_rooms,
                           rooms_from_rects, to_ascii as dungeon_to_ascii,
                           EDGE_OPEN, EDGE_LOCKED, EDGE_LOOP,
                           KIND_ENTRANCE, KIND_BOSS, KIND_TREASURE, KIND_GUARD)
from .dungeongraph import (Room, build_dungeon_graph, detect_rooms,
                           rooms_from_rects, to_ascii as dungeon_to_ascii,
                           EDGE_OPEN, EDGE_LOCKED, EDGE_LOOP,
                           KIND_ENTRANCE, KIND_BOSS, KIND_TREASURE, KIND_GUARD)

__all__ = [
    "value_noise", "perlin_noise", "fractal_noise", "fbm", "simplex_noise",
    "warp_noise", "ridged_noise", "cellular_noise",
    "generate_dungeon", "generate_dungeon_bsp", "generate_cave", "to_ascii",
    "generate_town",
    "NameGenerator", "GrammarGenerator", "grammar_names",
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
    "generate_world_full", "describe", "generate_world_complete", "describe_complete",
    "WATER_NONE", "WATER_RIVER", "WATER_LAKE", "WATER_SEA",
    # worldspec v1（三仓之间的文件契约）
    "save_world", "load_world", "read_meta", "validate",
    "WorldSpecError", "SPEC_NAME",
    # POI 选址 / 路网 / WFC
    "Poi", "place_pois", "describe_pois", "slope_field",
    "poisson_disk_sample", "place_pois_uniform",
    "KIND_TOWN", "KIND_VILLAGE", "KIND_PORT", "KIND_MINE", "KIND_RUIN",
    "KIND_LIGHTHOUSE", "KIND_BRIDGE", "KIND_FORD", "SETTLEMENT_KINDS",
    "build_road_network", "least_cost_path", "road_cost_field", "describe_network",
    "Tile", "TileSet", "wang_tileset", "generate_wfc", "rasterize",
    "generate_wfc_overlapping", "generate_dungeon_wfc", "WfcContradiction",
    # 地牢图（房间/走廊/锁钥/语义）
    "Room", "build_dungeon_graph", "detect_rooms", "rooms_from_rects",
    "dungeon_to_ascii", "EDGE_OPEN", "EDGE_LOCKED", "EDGE_LOOP",
    "KIND_ENTRANCE", "KIND_BOSS", "KIND_TREASURE", "KIND_GUARD",
]
