# worldbuilder 程序化生成库

> 仓库：<https://gitee.com/siwpan/worldbuilder> ｜ 许可：MIT（见 [LICENSE](LICENSE)）
> 注：文中 <PATH> 为路径占位符，请替换为你本机实际的目录 / 可执行文件路径。

供各游戏项目 `import` 复用的程序化生成工具包（纯 Python + numpy）。

## 📦 包名与安装

| 项目 | PyPI 发行名 | 导入名 | Gitee 仓库 |
| --- | --- | --- | --- |
| 本库 | `worldbuilder` | `worldbuilder` | [siwpan/worldbuilder](https://gitee.com/siwpan/worldbuilder) |

```bat
pip install worldbuilder
```

```python
import worldbuilder as wb
```

**包名沿革**：本库原名 `procgen`，2026-08-27 以该名发布首个 Gitee 发行版 `v1.0.0`。
现因 PyPI 上 `procgen` 已被 OpenAI 的 *Procgen Benchmark* 占用，发行名与导入名统一更名为 `worldbuilder`，
版本号沿用 `1.0.0`（对外身份变更，功能面未变）。
Gitee 仓库路径同步更名为 `siwpan/worldbuilder`（旧路径 `siwpan/procgen` 由 Gitee 自动重定向），
路径与发行名现已一致——两者都请以 `worldbuilder` 为准。

> 历史版本导入的是 `import procgen as pg`；升级后请改为 `import worldbuilder as wb`。

## 模块
- `noise`：`value_noise` / `perlin_noise` / `fractal_noise` / `fbm`（可调 lacunarity/gain）/ `simplex_noise`（方向伪影更少的改进版）
- `dungeon`：`generate_dungeon`（随机房间）/ `generate_dungeon_bsp`（二叉空间分割，保证连通）/ `generate_cave`（元胞自动机洞穴）/ `to_ascii(grid)` 打印
- `namegen`：`NameGenerator(style, method)`，风格 fantasy/sci/eastern，方法 syllable（音节拼接）/ markov（字符级转移学习）
- `loot`：`LootTable(entries).roll(n, unique=...)` 加权随机掉落，`unique=True` 无重复
- `terrain`：`generate_heightmap`（支持 `falloff` 岛屿）/ `classify` / `generate_terrain` / `generate_moisture` / `classify_biomes`（Whittaker 生物群系，8 类可达）/ `generate_world`
- `town`：`generate_town(seed, n_wards, walled)` —— 从零移植自 watabou 中世纪奇幻城市生成器：Voronoi 划区 + 城墙(塔楼/城门) + 图寻路路网 + ward 加权分配 + 建筑递归分割。返回 {bounds, center, wall, streets, wards, ...}，坐标为抽象单位
- `road`：`gobi_corridor(rows, cols, extent, seed, ...)` —— 把**公路走廊挖进分形地形**：走廊 `|across| < road_half` 压平到 `corridor_level`、外侧用 `smoothstep` 过渡（硬切会产生锯齿法线）、背景叠加 ridged 远山；返回 `(hm, coords_x, coords_z)`。配套 `sample_height(hm, x, z, height, y_base)` 双线性采样（道具贴地）与 `smoothstep(t)`
- `hydro`：**水文科**。`fill_depressions`（Priority-Flood 填洼，边界为出水口）/ `flow_directions`（D8）/ `flow_accumulation`（按高程降序累积）/ `extract_rivers`（抽折线，`threshold` 缺省按 `格数/80` 自适应）/ `lakes` / `coastline` / `river_width`（`w ∝ Q^0.5`）/ `hydrology` 一次跑完
- `climate`：**气候科**。`temperature_map`（纬度余弦带 − 高度递减）/ `precipitation_map`（沿盛行风逐列输运 + 地形抬升致雨，产生雨影）/ `classify_biomes_climate`（12 类 Whittaker）/ `climate_maps` 一次跑完
- `worldspec`：**三仓之间的文件契约**（`save_world` / `load_world` / `read_meta` / `validate`）。
  产物目录自描述：`meta.json`（spec 版本/尺寸/海平面/坐标约定/tile_m/seed）+ `height.f32.npy`
  + `biome.u8.npy` + `water.u8.npy` + `temperature/precip` + `rivers.geojson`（LineString）+ `lakes.json`。
  **只共享格式，不共享代码**——3dworld / an-engine 各自读自己需要的层。
- `worldspec`：**三仓之间的文件契约**（`save_world` / `load_world` / `read_meta` / `validate`）。
  产物目录自描述：`meta.json`（spec 版本/尺寸/海平面/坐标约定/tile_m/seed）+ `height.f32.npy`
  + `biome.u8.npy` + `water.u8.npy` + `temperature/precip` + `rivers.geojson`（LineString）+ `lakes.json`。
  **只共享格式，不共享代码**——3dworld / an-engine 各自读自己需要的层。
- `worldgen`：**编排**。`generate_world_full(...)` 按「高度 → 海平面 → 填洼 → 流向 → 汇水 → 河/湖/海岸 → 温度 → 降水 → 群系」固定顺序产出全层数据；`describe(world)` 打一行摘要

## 用法
```python
import sys; sys.path.insert(0, r"<PATH>")
import worldbuilder as wb

hm = wb.generate_heightmap(64, 64, seed=1)
d  = wb.generate_dungeon(48, 32, rooms=8, seed=2)
bsp = wb.generate_dungeon_bsp(60, 40, seed=5)          # BSP 地牢
cave = wb.generate_cave(56, 40, seed=7)                # 洞穴
names = wb.NameGenerator(style='fantasy').generate(10)
mkv = wb.NameGenerator(style='sci', method='markov').generate(10)
drops = wb.LootTable([("金币",50,(1,10)),("传说剑",1,(1,1))]).roll(5)
uniq = wb.LootTable([("a",50,(1,2)),("b",30,(1,2))]).roll(3, unique=True)
wld = wb.generate_world(80, 80, seed=11, falloff=0.3)  # 含生物群系
sx = wb.simplex_noise(xs, ys, seed=1)                  # 2D simplex
```

### 整套世界（水文 + 气候 + 群系）

```python
w = wb.generate_world_full(160, 160, seed=7, falloff=0.35)
print(wb.describe(w))
# 尺寸 160x160 | seed=7 | 海平面=0.334
# 河流 16 条 | 湖泊 111 个 | 海岸格 2460
# 群系：水域 35.0%、苔原 20.0%、热带沙漠 10.8%、温带草原 7.5%、海滩 6.0%、…

w["height"]        # float32 高度图
w["water"]         # uint8：0 无 / 1 河 / 2 湖 / 3 海
w["rivers"][0]     # {"points": [(x, y), ...], "mouth": ..., "acc_max": ...}
w["biomes"]        # int8，12 类，见 wb.CLIMATE_BIOME_NAMES
w["temperature"]   # °C；w["precipitation"] 是 0..1 相对指数
```

落成 worldspec 目录，交给渲染端/玩法端：

```python
meta = wb.save_world(w, "worlds/seed7")      # 写 meta.json + 6 个 npy + 2 个 json
back = wb.load_world("worlds/seed7", layers=("height", "water"))   # 只取要用的层
assert wb.validate("worlds/seed7") == []      # 体检：缺层/形状不符/坏 GeoJSON 都会列出来
```

落成 worldspec 目录，交给渲染端/玩法端：

```python
meta = wb.save_world(w, "worlds/seed7")      # 写 meta.json + 6 个 npy + 2 个 json
back = wb.load_world("worlds/seed7", layers=("height", "water"))   # 只取要用的层
assert wb.validate("worlds/seed7") == []      # 体检：缺层/形状不符/坏 GeoJSON 都会列出来
```

只要水系或只要气候，也可以拆开用：

```python
hy = wb.hydrology(hm, sea_level=0.34)      # filled/dirs/acc/rivers/lakes/coast
cl = wb.climate_maps(hm, wind_from_deg=270, sea_level=0.34)
```

## 命令行演示
```bat
cd <PATH>
python cli.py terrain --size 64 --seed 1 --out terrain.png
python cli.py dungeon --w 48 --h 32 --rooms 8
python cli.py name --style fantasy --n 10
python cli.py loot --n 5
```

## 示例

example/ 目录是一个完整的实操示例（冒险者公会任务包生成器），串起噪声/地形/地牢/洞穴/命名/掉落并渲染 PNG 成果包：

```bat
cd <PATH>\example
python run.py --seed 7
```

## 说明
- 本库是独立包，**不依赖 tools 组其他项目**，可直接复制到任意游戏工程内使用（复制优于共享）。
- 所有随机均带 seed，可复现。
- 网格约定：`1`=可走/地板，`0`=墙（dungeon 与 cave 一致）。
- **纬度约定**：`temperature_map` 缺省把整幅图的 y 轴铺满 `+90°…-90°`（即"一张全球图"）。
  做**区域图**时请显式传 `latitude=` 或改用 `climate_maps(..., latitude=...)`，
  否则一张 64 行的小地图也会同时出现极地和赤道。
- **降水是相对指数**（0..1）：原始量是"每列降掉水汽的比例"，按 `reference=0.08` 归一。
  `reference` 调小 → 世界更湿。别把它当毫米年降水量用。
- **成河阈值**缺省 `格数/80`：实测 96²/192²/256² 在同一 seed 下都落在 18~22 条主干河，
  即**河数不随分辨率漂移**；要更密/更疏直接传 `river_threshold=`。
- **性能**：256² 全链路（含填洼、河流、气候）约 0.35 s（纯 numpy，无 numba）。
  填洼是 Python 堆实现的 O(n log n)，单次上限 400 万格（`fill_depressions(max_cells=...)`）。
