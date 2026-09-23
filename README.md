# procgen 程序化生成库

> 仓库：<https://gitee.com/siwpan/procgen> ｜ 许可：MIT（见 [LICENSE](LICENSE)）
> 注：文中 <PATH> 为路径占位符，请替换为你本机实际的目录 / 可执行文件路径。

供各游戏项目 `import` 复用的程序化生成工具包（纯 Python + numpy）。

## 模块
- `noise`：`value_noise` / `perlin_noise` / `fractal_noise` / `fbm`（可调 lacunarity/gain）/ `simplex_noise`（方向伪影更少的改进版）
- `dungeon`：`generate_dungeon`（随机房间）/ `generate_dungeon_bsp`（二叉空间分割，保证连通）/ `generate_cave`（元胞自动机洞穴）/ `to_ascii(grid)` 打印
- `namegen`：`NameGenerator(style, method)`，风格 fantasy/sci/eastern，方法 syllable（音节拼接）/ markov（字符级转移学习）
- `loot`：`LootTable(entries).roll(n, unique=...)` 加权随机掉落，`unique=True` 无重复
- `terrain`：`generate_heightmap`（支持 `falloff` 岛屿）/ `classify` / `generate_terrain` / `generate_moisture` / `classify_biomes`（Whittaker 生物群系，8 类可达）/ `generate_world`
- `town`：`generate_town(seed, n_wards, walled)` —— 从零移植自 watabou 中世纪奇幻城市生成器：Voronoi 划区 + 城墙(塔楼/城门) + 图寻路路网 + ward 加权分配 + 建筑递归分割。返回 {bounds, center, wall, streets, wards, ...}，坐标为抽象单位

## 用法
```python
import sys; sys.path.insert(0, r"<PATH>")
import procgen as pg

hm = pg.generate_heightmap(64, 64, seed=1)
d  = pg.generate_dungeon(48, 32, rooms=8, seed=2)
bsp = pg.generate_dungeon_bsp(60, 40, seed=5)          # BSP 地牢
cave = pg.generate_cave(56, 40, seed=7)                # 洞穴
names = pg.NameGenerator(style='fantasy').generate(10)
mkv = pg.NameGenerator(style='sci', method='markov').generate(10)
drops = pg.LootTable([("金币",50,(1,10)),("传说剑",1,(1,1))]).roll(5)
uniq = pg.LootTable([("a",50,(1,2)),("b",30,(1,2))]).roll(3, unique=True)
wld = pg.generate_world(80, 80, seed=11, falloff=0.3)  # 含生物群系
sx = pg.simplex_noise(xs, ys, seed=1)                  # 2D simplex
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
cd G:	oolsgameprocgenexample
python run.py --seed 7
```

## 说明
- 本库是独立包，**不依赖 tools 组其他项目**，可直接复制到任意游戏工程内使用（复制优于共享）。
- 所有随机均带 seed，可复现。
- 网格约定：`1`=可走/地板，`0`=墙（dungeon 与 cave 一致）。
