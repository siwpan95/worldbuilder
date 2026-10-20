"""run.py —— 基于 worldbuilder 的“冒险者公会任务包”生成器（实操）。

把 worldbuilder 库里的：地形/生物群系、随机房间地牢、BSP 地牢、元胞自动机洞穴、
噪声（value/perlin/fbm/simplex）、名字生成（音节/马尔可夫）、掉落表
全部串起来，产出一份可直接查看的成果包，落到本目录的 output\\。

运行：
    python run.py            # 使用内置演示参数
    python run.py --seed 7   # 换种子生成另一套

依赖：worldbuilder（位于本示例的上一级目录，即仓库根下的 worldbuilder 包）、numpy、Pillow
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings

import numpy as np

# ---- 让 worldbuilder 根目录（本示例的上一级）可被 import ----
HERE = os.path.dirname(os.path.abspath(__file__))
WB_ROOT = os.path.dirname(HERE)
if WB_ROOT not in sys.path:
    sys.path.insert(0, WB_ROOT)
import worldbuilder as wb
from worldbuilder.dungeon import to_ascii

from render import (grid_to_png, classes_to_png, gray_to_png,
                    grid_to_ascii_png, BIOME_PALETTE, TERRAIN_PALETTE, add_legend)

OUT = os.path.join(HERE, "output")


# ---------------------------------------------------------------------------
# 1. 世界 / 生物群系
# ---------------------------------------------------------------------------
def make_world(seed: int) -> dict:
    # 大陆版：无衰减，便于完整展示 8 类生物群系
    # 对高度图做 min-max 归一化拉伸（程序化地形常见预处理），让全梯度呈现，
    # 否则 fBm 输出罕见 >=0.75，山/雪/苔几乎不出现。
    hm = wb.generate_heightmap(64, 64, seed=seed, scale=0.07, octaves=5, falloff=0.0)
    moist = wb.generate_moisture(64, 64, seed=seed)
    lo, hi = float(hm.min()), float(hm.max())
    hm_n = (hm - lo) / (hi - lo) if hi > lo else hm
    biomes = wb.classify_biomes(hm_n, moist)
    dist = {wb.BIOME_NAMES[k]: int((biomes == k).sum()) for k in range(8)}
    path = os.path.join(OUT, "world_biomes.png")
    classes_to_png(biomes, BIOME_PALETTE).save(path)
    add_legend(path, "生物群系", [(wb.BIOME_NAMES[k], BIOME_PALETTE[k]) for k in range(8)])
    gray_to_png(hm).save(os.path.join(OUT, "world_heightmap.png"))
    gray_to_png(moist).save(os.path.join(OUT, "world_moisture.png"))

    # 岛屿版：径向衰减，演示 falloff 形成海岛
    himg = wb.generate_heightmap(64, 64, seed=seed, scale=0.07, octaves=5, falloff=0.35)
    lo2, hi2 = float(himg.min()), float(himg.max())
    himg_n = (himg - lo2) / (hi2 - lo2) if hi2 > lo2 else himg
    island = wb.classify_biomes(himg_n, moist)
    ipath = os.path.join(OUT, "world_island.png")
    classes_to_png(island, BIOME_PALETTE).save(ipath)
    add_legend(ipath, "岛屿版", [(wb.BIOME_NAMES[k], BIOME_PALETTE[k]) for k in range(8)])
    return {"dist": dist, "seed": seed}


# ---------------------------------------------------------------------------
# 2. 地牢：随机房间 + BSP
# ---------------------------------------------------------------------------
def make_dungeons(seed: int) -> dict:
    # 随机房间式
    d1 = wb.generate_dungeon(48, 32, rooms=9, seed=seed)
    grid_to_png(d1["grid"]).save(os.path.join(OUT, "dungeon_rooms.png"))
    grid_to_ascii_png(d1["grid"]).save(os.path.join(OUT, "dungeon_rooms_ascii.png"))
    # BSP 式
    d2 = wb.generate_dungeon_bsp(48, 32, seed=seed)
    grid_to_png(d2["grid"]).save(os.path.join(OUT, "dungeon_bsp.png"))
    grid_to_ascii_png(d2["grid"]).save(os.path.join(OUT, "dungeon_bsp_ascii.png"))
    return {
        "rooms_simple": len(d1["rooms"]),
        "rooms_bsp": len(d2["rooms"]),
        "connections_simple": len(d1["connections"]),
        "connections_bsp": len(d2["connections"]),
    }


# ---------------------------------------------------------------------------
# 3. 洞穴（元胞自动机）
# ---------------------------------------------------------------------------
def make_cave(seed: int) -> dict:
    c = wb.generate_cave(56, 40, seed=seed, fill_prob=0.45, iterations=5)
    grid_to_png(c["grid"]).save(os.path.join(OUT, "cave.png"))
    grid_to_ascii_png(c["grid"]).save(os.path.join(OUT, "cave_ascii.png"))
    return {"regions": c["regions"], "floor_count": c["floor_count"]}


# ---------------------------------------------------------------------------
# 4. 噪声对比（value / perlin / fbm / simplex）
# ---------------------------------------------------------------------------
def make_noise(seed: int) -> dict:
    size = 64
    xs, ys = np.meshgrid(np.arange(size), np.arange(size))
    # 用缩放后的分数坐标，避免整数格点退化为 0.5
    fx, fy = xs * 0.08, ys * 0.08
    vn = wb.value_noise(fx, fy, seed=seed)
    pn = wb.perlin_noise(fx, fy, seed=seed)
    fn = wb.fbm(fx, fy, octaves=5, seed=seed)
    sn = wb.simplex_noise(fx, fy, seed=seed)
    gray_to_png(vn).save(os.path.join(OUT, "noise_value.png"))
    gray_to_png(pn).save(os.path.join(OUT, "noise_perlin.png"))
    gray_to_png(fn).save(os.path.join(OUT, "noise_fbm.png"))
    gray_to_png(sn).save(os.path.join(OUT, "noise_simplex.png"))
    return {}


# ---------------------------------------------------------------------------
# 5. 名字生成（音节 + 马尔可夫，三种风格）
# ---------------------------------------------------------------------------
def make_names(seed: int) -> dict:
    out = {}
    for style in ("fantasy", "sci", "eastern"):
        syl = wb.NameGenerator(style=style, seed=seed, method="syllable").generate(8)
        mk = wb.NameGenerator(style=style, seed=seed, method="markov").generate(8)
        out[style] = {"syllable": syl, "markov": mk}
    return out


# ---------------------------------------------------------------------------
# 6. 掉落表
# ---------------------------------------------------------------------------
def make_loot(seed: int) -> dict:
    table = wb.LootTable([
        ("金币", 50, (1, 10)),
        ("药水", 10, (1, 3)),
        ("宝石", 5, (1, 2)),
        ("符文", 3, (1, 1)),
        ("传说剑", 1, (1, 1)),
    ], seed=seed)
    return {
        "chest": table.roll(5),            # 普通宝箱：5 次抽取
        "unique": table.roll(3, unique=True),  # 限定掉落：不重复
    }


# ---------------------------------------------------------------------------
# 7. 城镇（移植自 watabou 的中世纪奇幻城市生成器）
# ---------------------------------------------------------------------------
def make_town(seed: int) -> dict:
    from render import town_to_png
    town = wb.generate_town(seed, n_wards=15, walled=True)
    town_to_png(town, scale_to=900).save(os.path.join(OUT, "town.png"))
    dist = {}
    for w in town["wards"]:
        dist[w["type"]] = dist.get(w["type"], 0) + 1
    return {
        "wards": len(town["wards"]),
        "wall": town["wall"] is not None,
        "gates": len(town["wall"]["gates"]) if town["wall"] else 0,
        "streets": len(town["streets"]),
        "buildings": sum(len(w["buildings"]) for w in town["wards"]),
        "dist": dist,
    }


# ---------------------------------------------------------------------------
# 汇总报告
# ---------------------------------------------------------------------------
def write_report(seed, world, dungeons, cave, names, loot, town):
    lines = []
    lines.append("# 冒险者公会任务包（worldbuilder 实操成果）")
    lines.append("")
    lines.append(f"- 种子 seed = {seed}")
    lines.append("- 生成时间由运行环境决定；输出目录：<PATH>\example\output")
    lines.append("")
    lines.append("## 1. 世界与生物群系 (generate_world)")
    lines.append("")
    lines.append("| 群系 | 格数 |")
    lines.append("| --- | --- |")
    for k, v in world["dist"].items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("![生物群系](output/world_biomes.png)  ![高度图](output/world_heightmap.png)")
    lines.append("")
    lines.append("岛屿版（falloff=0.35，演示径向衰减成岛）：")
    lines.append("")
    lines.append("![岛屿版](output/world_island.png)")
    lines.append("")
    lines.append("## 2. 地牢 (generate_dungeon / generate_dungeon_bsp)")
    lines.append("")
    lines.append(f"- 随机房间式：{dungeons['rooms_simple']} 房间 / "
                 f"{dungeons['connections_simple']} 连接")
    lines.append(f"- BSP 式：{dungeons['rooms_bsp']} 房间 / "
                 f"{dungeons['connections_bsp']} 连接")
    lines.append("")
    lines.append("![房间地牢](output/dungeon_rooms.png)  ![BSP地牢](output/dungeon_bsp.png)")
    lines.append("")
    lines.append("## 3. 洞穴 (generate_cave, 元胞自动机)")
    lines.append("")
    lines.append(f"- 连通块数：{cave['regions']}，最大可走地板格数：{cave['floor_count']}")
    lines.append("")
    lines.append("![洞穴](output/cave.png)")
    lines.append("")
    lines.append("## 4. 噪声对比 (value / perlin / fbm / simplex)")
    lines.append("")
    lines.append("![value](output/noise_value.png) ![perlin](output/noise_perlin.png)")
    lines.append("![fbm](output/noise_fbm.png) ![simplex](output/noise_simplex.png)")
    lines.append("")
    lines.append("## 5. 名字生成 (NameGenerator, 音节 / 马尔可夫)")
    lines.append("")
    for style, d in names.items():
        lines.append(f"### {style}")
        lines.append("- 音节拼接：" + "、".join(d["syllable"]))
        lines.append("- 马尔可夫：" + "、".join(d["markov"]))
        lines.append("")
    lines.append("## 6. 掉落表 (LootTable)")
    lines.append("")
    lines.append("- 普通宝箱（5 抽）：" + "、".join(loot["chest"]))
    lines.append("- 限定掉落（不重复 3 抽）：" + "、".join(loot["unique"]))
    lines.append("")
    lines.append("## 7. 城镇 (generate_town)")
    lines.append("")
    lines.append(f"- 区划数：{town['wards']}，带城墙：{town['wall']}，"
                 f"城门：{town['gates']}，街道：{town['streets']}，建筑：{town['buildings']}")
    lines.append("")
    lines.append("| ward 类型 | 数量 |")
    lines.append("| --- | --- |")
    for k, v in sorted(town["dist"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("![城镇](output/town.png)")
    lines.append("")
    lines.append("> 说明：`generate_town` 从零移植自 watabou 的 Medieval Fantasy City "
                 "Generator（Haxe/OpenFL），复刻其 Voronoi 划区 + Lloyd 松弛、城墙"
                 "（塔楼/城门）、图寻路路网、ward 加权分配与建筑递归分割等核心算法，"
                 "以纯 Python + numpy 实现，无外部图形依赖。")
    lines.append("")
    lines.append("## 附：实操观察")
    lines.append("")
    lines.append("- `classify_biomes` 中 TUNDRA（苔原）分支存在逻辑冲突：它要求 "
                 "`temperature<0.25`（即 `hm>0.75`），但同一条语句又被限定在 "
                 "`low = hm<0.75` 的集合内，导致苔原在默认参数下永远无法出现"
                 "（本包中苔原格数恒为 0）。这是 worldbuilder 库的一个待修复点。")
    lines.append("- 生物群系图对高度图做了 min-max 归一化拉伸，否则 fBm 输出罕见 >=0.75，"
                 "山/雪几乎不出现；这是程序化地形常见的对比度预处理。")
    lines.append("")
    path = os.path.join(HERE, "report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def main():
    ap = argparse.ArgumentParser(description="worldbuilder 实操：冒险者公会任务包生成器")
    ap.add_argument("--seed", type=int, default=20260717)
    args = ap.parse_args()
    seed = args.seed

    os.makedirs(OUT, exist_ok=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        print(f"[1/6] 生成世界/生物群系 seed={seed} ...")
        world = make_world(seed)
        print(f"      群系分布: {world['dist']}")

        print("[2/6] 生成地牢（随机房间 + BSP）...")
        dungeons = make_dungeons(seed)
        print(f"      房间数: simple={dungeons['rooms_simple']} bsp={dungeons['rooms_bsp']}")

        print("[3/6] 生成元胞自动机洞穴...")
        cave = make_cave(seed)
        print(f"      区域={cave['regions']} 地板={cave['floor_count']}")

        print("[4/6] 生成噪声对比图...")
        make_noise(seed)

        print("[5/6] 生成名字清单...")
        names = make_names(seed)

        print("[6/6] 生成掉落清单 + 汇总报告...")
        loot = make_loot(seed)

    print("[7/7] 生成城镇（移植自 watabou 城市生成器）...")
    town = make_town(seed)

    report = write_report(seed, world, dungeons, cave, names, loot, town)
    print(f"[OK] 完成。报告: {report}")
    print(f"     图片与数据位于: {OUT}")


if __name__ == "__main__":
    main()
