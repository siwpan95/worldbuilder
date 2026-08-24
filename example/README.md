# procgen 示例：冒险者公会任务包生成器（example）

基于本仓库（`G:\tools\game\procgen`）的程序化生成库，落地一个可直接查看的「成果包」：
把噪声 / 地形 / 地牢 / 洞穴 / 命名 / 掉落全部串起来，渲染成 PNG 地图与清单。

## 运行

```bat
cd G:\tools\game\procgen\example
python run.py            REM 使用默认种子 20260717
python run.py --seed 7   REM 换种子生成另一套世界
```

依赖：
- `G:\tools\game\procgen`（本示例的上一级目录；`requirements.txt` 声明 numpy + Pillow）
- 本机已具备：Python 3.14、numpy、Pillow

## 产出

`G:\tools\game\procgen\example\output\` 下：

| 文件 | 内容 | 对应 procgen API |
| --- | --- | --- |
| `world_biomes.png` | 生物群系地图（带图例，8 色） | `generate_heightmap`+`classify_biomes` |
| `world_island.png` | 岛屿版（径向衰减成岛） | `falloff` 参数 |
| `world_heightmap.png` | 高度图灰度 | `generate_heightmap` |
| `world_moisture.png` | 湿度图灰度 | `generate_moisture` |
| `dungeon_rooms.png` / `_ascii.png` | 随机房间地牢（图 + ASCII） | `generate_dungeon` |
| `dungeon_bsp.png` / `_ascii.png` | BSP 地牢（图 + ASCII） | `generate_dungeon_bsp` |
| `cave.png` / `_ascii.png` | 元胞自动机洞穴（图 + ASCII） | `generate_cave` |
| `noise_value.png` / `noise_perlin.png` / `noise_fbm.png` / `noise_simplex.png` | 四种噪声对比 | `value_noise`/`perlin_noise`/`fbm`/`simplex_noise` |
| `town.png` | 城镇地图（城墙/城门/塔楼/路网/建筑/ward 配色） | `generate_town` |

汇总报告见 `G:\example\report.md`（含名字清单、掉落清单、城镇区划与观察笔记）。

## 文件说明

- `run.py` —— 主生成器，串起全部模块并落盘。
- `render.py` —— 纯 numpy + Pillow 的「数值 → 图片/ASCII」渲染工具，不依赖 procgen，
  便于复用。

## 7. 城镇生成器（generate_town）

`procgen.town` 从零移植自 watabou 的 **Medieval Fantasy City Generator**
（Haxe/OpenFL，渲染耦合 Flash 图形 API，无法直接 import），以纯 Python + numpy
复刻其核心管线：

1. **Voronoi 划区**：种子点按 phyllotaxis 螺旋散布 → 建立 Delaunay/Voronoi 图 →
   对中心区做 Lloyd 松弛 → 得到城市街区
2. **城墙（CurtainWall）**：求外边界多边形、布置塔楼与城门
3. **路网（Topology）**：在 patch 顶点图上做最短路（Dijkstra），把每座城门连到中心
4. **区划分配**：`WARDS` 权重表 + `rateLocation` 选址，给每个街区分配类型
   （集市/城堡/工匠/商人/贫民/贵族/行政/军事/公园/农场/大教堂…）
5. **建筑几何**：各 ward 用递归二分（`createAlleys`）+ 正交切割（`createOrthoBuilding`）
   生成多边形建筑地块

`G:\example\run.py` 的 `make_town()` 调用 `pg.generate_town(seed, n_wards=15, walled=True)`
并把结果交给 `render.town_to_png()` 渲染成 `town.png`。换种子即可生成不同城镇。

## 实操观察

- **苔原 bug 已修复**：`classify_biomes` 原 TUNDRA 分支条件自相矛盾（要求 `temperature<0.25`
  即 `hm>0.75`，却又被限定在 `low=hm<0.75` 内），导致苔原恒为 0。已在 `procgen/terrain.py`
  改为按海拔带划分（苔原 0.75~0.85、雪 ≥0.85），现 8 类群系全部可达（详见 `report.md`）。
- 生物群系图对高度图做了 min-max 归一化拉伸，否则山/雪几乎不出现。
- 城镇生成器为「算法移植」而非二进制依赖：`G:\1\TownGeneratorOS-master` 仅作架构参考，
  全部几何/管线已用纯 Python 重写，无 OpenFL 依赖。
