# Changelog

本项目所有值得注意的变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.1] - 2026-10-21

> 专项压测暴露的 4 处缺陷修复。

### Fixed

- **noise.perlin_noise / fbm**：输入全部落在整数格点时输出恒为 0.5（高程场被静默抹平）。
  补充文档说明，并在检测到整点网格时发出 `UserWarning`，提示按波长缩放坐标（`x*freq`）避开整点。
- **town.distance2line**：方向向量为零时由裸 `ZeroDivisionError` 改为
  `ValueError: 方向向量不能为零向量 (dx1, dy1)`。
- **town.Voronoi.build**：空顶点集由泄漏实现细节的 `min() ... is empty` 改为
  `ValueError: vertices 不能为空（Voronoi 需要至少 1 个种子点）`。
- **town._build_walls / _build_streets**：原公开名 `build_walls` / `build_streets` 消费的是
  `generate_town` 的内部 model（含 `inner` / `patches` / `gates`），与公开返回 dict 的键不一致，
  外部调用必 `KeyError`。已改名为内部函数（`_` 前缀），并修正 `generate_town` 文档字符串
  （实际返回 `scale_to` 而非文档所写的 `patches`）。

## [1.0.0] - 2026-10-20（重建同名发行版）

> 说明：原 `v1.0.0`（2026-08-27，包名 `procgen`）已连同 Gitee release 一并删除重建，
> 以避免"包名 procgen / 包名 worldbuilder"两种身份共用同一版本号而互相矛盾。

### Changed

- **发行名与导入名 `procgen` → `worldbuilder`**（包目录 `procgen/` → `worldbuilder/`，示例别名 `pg` → `wb`）。
  原因：PyPI 上 `procgen` 已被 OpenAI 的 Procgen Benchmark 占用，与本库无关。
- Gitee 仓库路径保持不变（`siwpan/procgen`），**包名一律以 PyPI 为准**。

- **地牢图 `worldbuilder/dungeongraph.py`（P1-1 后半，2026-10-20）**：从网格抽关卡图。
  - `build_dungeon_graph(grid, rooms=None, locks=1, loops=2, seed=0)`：BSP 给矩形就直接用，
    否则用「3×3 全地板」核心认房间；薄墙地牢（WFC 十字房间）没有任何 3×3 空块，
    自动退化成「交叉口」核心。
  - 边 = 多源 BFS 穿走廊的第一次接触，路径保留为折线，**不穿过第三方房间**。
  - 语义：入口 = 离边界最近的房间；Boss = 图上离入口最远；宝箱优先放被锁子树里最深的房间；
    守卫 = 入口→Boss 路径上的中间房间。
  - 锁钥：只在**生成树深层边**上锁，钥匙放在「不经过任何锁即可从入口到达」的房间——
    这条是可解性的定义，`test_keys_reachable_without_any_lock` 直接钉住。
  - 输出 `nodes/edges` 与 worldspec 的 `graph.json` 同形，下游 `MapGraph` 可直接消费。
  - 修 bug 两处：走廊格曾被当成墙（导致一条边都连不上）；WFC 房间没有 3×3 核心。
  - 测试 +13（`tests/test_dungeongraph.py`），套件 112 → 125。

- 首次发布到 PyPI：`pip install worldbuilder`（sdist + wheel）。
- 打包元数据补全：作者、MIT 许可、keywords、classifiers、依赖声明。
- 依赖：仅 `numpy>=1.24.0`；CLI 绘图为可选 `Pillow`（`pip install worldbuilder[cli]`）。

## [Unreleased]

### Changed

- **Gitee 仓库路径 `siwpan/procgen` → `siwpan/worldbuilder`**：与发行名/导入名统一。
  旧路径由 Gitee 自动重定向，历史链接不失效；README 首行、包名沿革段与
  `pyproject.toml` 的 Homepage / Repository / Changelog 三个 URL 已同步。

- **地牢图 `worldbuilder/dungeongraph.py`（P1-1 后半，2026-10-20）**：从网格抽关卡图。
  - `build_dungeon_graph(grid, rooms=None, locks=1, loops=2, seed=0)`：BSP 给矩形就直接用，
    否则用「3×3 全地板」核心认房间；薄墙地牢（WFC 十字房间）没有任何 3×3 空块，
    自动退化成「交叉口」核心。
  - 边 = 多源 BFS 穿走廊的第一次接触，路径保留为折线，**不穿过第三方房间**。
  - 语义：入口 = 离边界最近的房间；Boss = 图上离入口最远；宝箱优先放被锁子树里最深的房间；
    守卫 = 入口→Boss 路径上的中间房间。
  - 锁钥：只在**生成树深层边**上锁，钥匙放在「不经过任何锁即可从入口到达」的房间——
    这条是可解性的定义，`test_keys_reachable_without_any_lock` 直接钉住。
  - 输出 `nodes/edges` 与 worldspec 的 `graph.json` 同形，下游 `MapGraph` 可直接消费。
  - 修 bug 两处：走廊格曾被当成墙（导致一条边都连不上）；WFC 房间没有 3×3 核心。
  - 测试 +13（`tests/test_dungeongraph.py`），套件 112 → 125。

- **聚落 / 路网 / WFC 地牢（P0-4，2026-10-20）**：把"有地理的世界"补成"有人的世界"。
  - `poi.py`：`place_pois()` 按水源、坡度、海拔带、群系与间距给每格打分，贪心选出
    `town` / `village` / `port` / `mine` / `ruin` / `lighthouse`。所有候选先限制在
    `main_landmass()`（**河算可通行**，否则一条贯穿全岛的河会把主陆块劈成两半），
    这一步是"遗迹被选到离岸孤岛、路修不过去"的直接修复。
    港口强制临海，矿强制在坡度上四分位，遗迹按"离聚落越远越高分"。
  - `roadnet.py`：`build_road_network()` 在代价场（坡度 + 涉水，海面 ∞）上跑 A*，
    8 邻接**禁切角**；聚落间先取 MST 再补 `loops` 条回路，矿/遗迹/灯塔接最近聚落
    （最近那个连不上就换下一个）。路在水面上的连续段自动生成 `bridge`（≤2 格）/
    `ford` 节点，过河点因此天然落在路真正要走的位置。
  - `wfc.py`：通用瓦片 WFC（熵最小 + 弧相容传播 + 有限回溯），`wang_tileset()` 生成
    15 个王瓦片（按通道数配权重），`generate_dungeon_wfc()` 直接产出 `(3h, 3w)` 的
    1/0 地牢网格，并**只保留最大连通块**，所以地板天然单连通。
  - `worldgen.generate_world_complete()`：一次跑完地形 → 水文 → 气候 → POI → 路网；
    `describe_complete()` 给定性摘要。
  - `worldspec` 新增两个**可选**图层：`pois.json`（GeoJSON Point）与 `graph.json`
    （nodes + edges，边带折线）。`meta` 声明数量，`validate()` 会检查 POI 越界、
    悬空边、折线少于 2 点。**只加文件不改字段**，旧消费方不受影响。
  - 测试 +45（`test_poi` / `test_roadnet` / `test_wfc` / `test_worldspec_graph`），
    套件 112 项。256² 全链路（含 27 条路、4 处过河）约 1.4 s。

- **水文 `worldbuilder/hydro.py`（P0-1）**：把"有水系的世界"补齐，顺序固定为
  填洼 → 流向 → 汇水 → 河流/湖泊/海岸。
  - `fill_depressions()`：Priority-Flood（Python 堆），边界为出水口，内部洼地抬到
    `出水口 + ε`，ε 让平地面也有微坡（否则 D8 在填平区没有方向）；
  - `flow_directions()`：D8 最陡下降，只在**严格更低**时给方向；
  - `flow_accumulation()`：按高程降序把汇水加到下游，纯东向斜面可闭式验证守恒；
  - `extract_rivers()`：从河源顺流抽折线，汇流处停下（干流优先占位）；
  - `lakes()` / `coastline()` / `river_width()`（`w ∝ Q^0.5`）/ `hydrology()` 一次跑完。
  - 成河阈值缺省 `格数/80`：**河数不随分辨率漂移**（96²/192²/256² 同 seed 均 18~22 条）。
- **气候 `worldbuilder/climate.py`（P0-2）**：把气候绑到地形上，不再是凭空一张湿度噪声。
  - `temperature_map()`：纬度余弦带（`cos^1.5`）+ 高度递减（默认 6.5℃/km）；
  - `precipitation_map()`：沿盛行风逐列输运水汽，**海面补到饱和**、陆地按抬升降雨 +
    背景对流；背风侧因水汽被抽干而自然变干（雨影）。非基本风向吸附到最近 N/E/S/W；
  - `classify_biomes_climate()`：12 类 Whittaker（含高山/海滩/水体覆盖）；
  - `climate_maps()` 一次跑完。
  - 口径：降水输出是**相对指数**（`reference=0.08` 归一），不是毫米年降水量。
- **编排 `worldbuilder/worldgen.py`**：`generate_world_full()` 按依赖顺序串起全部图层
  （高度 → 海平面 → 填洼 → 流向 → 汇水 → 河/湖/海岸 → 温度 → 降水 → 群系），
  返回 `height/filled/water/temperature/precipitation/biomes/rivers/lakes/coast/acc/meta`；
  `describe(world)` 打一行摘要。海平面可由 `sea_fraction` 分位数反推。
- **测试 39 项**：`tests/test_hydro.py`（14）、`tests/test_climate.py`（12）、
  `tests/test_worldgen.py`（13）。钉住的不变量包括：填洼只抬不降且不留内部洼地、
  填洼幂等且不动边界、汇水守恒与下游单调、河流收尾只能是边界/汇/汇流点、
  雨影随风向翻转、极地不会判成热带沙漠、同 seed 逐位可复现、老 8 类接口未变。
- **`worldbuilder/worldspec.py`（worldspec/1）**：三仓之间的**文件契约**。
  `save_world()` 把 `generate_world_full()` 的产物落成自描述目录（`meta.json` + 6 个 npy +
  `rivers.geojson` + `lakes.json`）；`load_world(layers=...)` 可按需只取几层；
  `read_meta()` 只读清单；`validate()` 返回问题清单（缺必需层 / 形状与 size 不符 /
  water 出现未定义编码 / GeoJSON 坏掉）。
  - 坐标约定写死在 meta：右手系、Y 向上、`height[r][c]` 的 r 对应 +z（与 3dworld 的行主序一致）、
    单位米、`tile_m` 给出格距；`spec` 字段严格匹配，不猜字段式兼容。
  - 跨仓实测：`save_world(256², tile_m=4)` → 3dworld `TerrainLod` 直接读 `height`，
    选层 40 节点 / 20,480 三角，覆盖检查 `min=max=1`、无空洞。
- **`tests/test_worldspec.py`**（14 项）：数组往返逐位一致、河流折线几何保真、只取子集图层、
  spec 版本拒读、缺必需层报错 / 缺可选层返回 None、形状不符拒读、`validate` 抓出坏 water 编码与
  伪 GeoJSON、同目录重跑不残留旧图层。
- **`worldbuilder/worldspec.py`（worldspec/1）**：三仓之间的**文件契约**。
  `save_world()` 把 `generate_world_full()` 的产物落成自描述目录（`meta.json` + 6 个 npy +
  `rivers.geojson` + `lakes.json`）；`load_world(layers=...)` 可按需只取几层；
  `read_meta()` 只读清单；`validate()` 返回问题清单（缺必需层 / 形状与 size 不符 /
  water 出现未定义编码 / GeoJSON 坏掉）。
  - 坐标约定写死在 meta：右手系、Y 向上、`height[r][c]` 的 r 对应 +z（与 3dworld 的行主序一致）、
    单位米、`tile_m` 给出格距；`spec` 字段严格匹配，不猜字段式兼容。
  - 跨仓实测：`save_world(256², tile_m=4)` → 3dworld `TerrainLod` 直接读 `height`，
    选层 40 节点 / 20,480 三角，覆盖检查 `min=max=1`、无空洞。
- **`tests/test_worldspec.py`**（14 项）：数组往返逐位一致、河流折线几何保真、只取子集图层、
  spec 版本拒读、缺必需层报错 / 缺可选层返回 None、形状不符拒读、`validate` 抓出坏 water 编码与
  伪 GeoJSON、同目录重跑不残留旧图层。
- 来由：原库只有"高度 → 生物群系"一条边，没有水系与气候，聚落/道路/生态都无从挂载。
  层的划分参考 Azgaar Fantasy Map Generator（MIT），算法实现自写；记录见 `docs/借鉴记账.md`。

- **噪声 v2：`warp_noise` / `ridged_noise` / `cellular_noise`**（`worldbuilder/noise.py`）：
  - `warp_noise(...)`：低频场扭曲坐标后再采样基噪声；`warp_strength=0` 时**逐位等于**基噪声直采；
  - `ridged_noise(...)`：`1-|2n-1|` 取脊 + `sharpness` 幂次 + 逐层归一；
  - `cellular_noise(...)`：Worley f1 / f2 / f2-f1，3×3 邻域全程向量化，`jitter` 可调。
  - 旧函数**一行未改**；新参数均有默认值，老调用输出逐位不变（黄金值测试，含 dtype/shape）。
  - 借鉴 FastNoiseLite（MIT）的算法口径，实现自写；记录见 `docs/借鉴记账.md`。
- **`tests/test_noise_v2.py`**：20 项（兼容性黄金值 / 三种子类型不变量 / 同 seed 复现 / 标量与广播）。
- **`docs/借鉴记账.md`**：本仓借鉴台账（watabou 仅取算法思想、FastNoiseLite 算法口径、后续 Azgaar/WFC 预登记）。
- **`worldbuilder/road.py`**（公路走廊）：`gobi_corridor()` 把公路"挖"进
  `noise.fractal_noise` 生成的分形地形——路基压平到 `corridor_level`、路侧用
  `smoothstep` 过渡、背景叠 ridged 远山；返回 `(hm, coords_x, coords_z)`。
  配套 `sample_height()`（双线性贴地采样）与 `smoothstep()`。
  已在 `__init__` 顶层导出，可 `wb.gobi_corridor(...)` 直接使用。
- **`test_road.py`**：5 组断言（走廊压平且整行等高 / 远山抬升 / 同 seed 逐位一致 /
  `sample_height` 精确值 / smoothstep 端点性质）。
- 来由：短剧《最后一百公里》的戈壁公路场景需要一个能直接喂给渲染端
  heightfield 的地形源（原先只有自然地表 `terrain.py`，没有道路能力）。

### 已作废

- 原 `## [1.0.0] - 2026-08-27`（旧包名 `procgen` 的首个 Gitee 发行版）已删除重建。
