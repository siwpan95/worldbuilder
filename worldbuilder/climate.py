"""气候：纬度温度带 + 高度递减 + 风向雨影 + Whittaker 生物群系（12 类）。

此前 ``terrain.generate_moisture`` 是"凭空一张湿度噪声"——湿度与地形无关，
于是沙漠可能出现在雨影之外的迎风坡，极地也可能长雨林。本模块把气候绑到地形上：

    温度 = 纬度余弦带 − 高度递减（lapse rate）
    降水 = 沿盛行风的水汽输送 − 地形抬升致雨（迎风湿、背风干）

降水模型是一维扫描：沿风向逐列推进，水汽每格蒸散补充、遇地形抬升按比例降落。
只用 4 个基本风向（N/E/S/W），其它角度按最近的基本风向吸附——这是刻意的简化，
换来的是纯 numpy、无迭代收敛、结果可解释可测试。

层的划分参考 Azgaar Fantasy Map Generator（MIT）的「温度/降水 → 生物群系」顺序，
算法与实现自写。
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np

#: 基本风向（气象学"风从哪来"）：0=N, 90=E, 180=S, 270=W
_CARDINALS = ("N", "E", "S", "W")

# 生物群系编码（12 类；与 terrain.py 的 8 类 BIOME_NAMES 并存，互不影响）
WATER, BEACH, TROPICAL_RAINFOREST, SAVANNA, HOT_DESERT = 0, 1, 2, 3, 4
TEMPERATE_FOREST, TEMPERATE_RAINFOREST, GRASSLAND, COLD_DESERT = 5, 6, 7, 8
TAIGA, TUNDRA, ALPINE = 9, 10, 11

CLIMATE_BIOME_NAMES: Dict[int, str] = {
    WATER: "水域",
    BEACH: "海滩",
    TROPICAL_RAINFOREST: "热带雨林",
    SAVANNA: "稀树草原",
    HOT_DESERT: "热带沙漠",
    TEMPERATE_FOREST: "温带森林",
    TEMPERATE_RAINFOREST: "温带雨林",
    GRASSLAND: "温带草原",
    COLD_DESERT: "温带荒漠",
    TAIGA: "泰加林",
    TUNDRA: "苔原",
    ALPINE: "高山",
}


def _snap_wind(wind_from_deg: float) -> Tuple[str, float]:
    """把任意风向吸附到最近的基本风向，返回 (代号, 规范化角度)。"""
    k = int(round(float(wind_from_deg) / 90.0)) % 4
    return _CARDINALS[k], float(k * 90.0)


def temperature_map(height: np.ndarray, latitude: Optional[np.ndarray] = None,
                    sea_level: float = 0.0, height_scale_m: float = 1000.0,
                    equator_c: float = 28.0, pole_c: float = -25.0,
                    lapse_c_per_km: float = 6.5,
                    north_up: bool = True) -> np.ndarray:
    """年均温（摄氏度）。

    参数：
        height:         高度图（0..1 归一化，或用 ``height_scale_m`` 折算成米）
        latitude:       每行的纬度（度，-90..90）。缺省按 ``north_up`` 在图上线性铺开
        height_scale_m: 高度 1.0 对应多少米（默认 1000 m）
        north_up:       True 表示第 0 行是北（纬度 +90），False 则相反
    返回 float32 数组，单位 °C。
    """
    h = np.asarray(height, dtype=np.float64)
    rows = h.shape[0]
    if latitude is None:
        lat = np.linspace(90.0 if north_up else -90.0,
                          -90.0 if north_up else 90.0, rows)
    else:
        lat = np.asarray(latitude, dtype=np.float64).reshape(-1)
        if lat.size != rows:
            raise ValueError(f"latitude 长度 {lat.size} 与行数 {rows} 不符")

    # 余弦带：赤道最热、两极最冷；1.5 次幂让热带范围收窄一些（更接近实际）
    band = pole_c + (equator_c - pole_c) * np.power(
        np.maximum(np.cos(np.deg2rad(lat)), 0.0), 1.5)
    temp = np.repeat(band[:, None], h.shape[1], axis=1)

    alt_km = np.clip(h - sea_level, 0.0, None) * (height_scale_m / 1000.0)
    temp -= lapse_c_per_km * alt_km
    return temp.astype(np.float32)


def _sweep_east(h: np.ndarray, sea_level: float, height_scale_m: float,
                capacity: float, evaporation: float, orographic: float,
                background: float) -> np.ndarray:
    """沿 +x（自西向东）扫描的水汽模型，返回 0..1 的降水场。

    关键设定（第一版栽过的坑）：
    - **海面把水汽补到饱和**。若只按 ``evaporation`` 逐格累加，60 列下来水汽还不到 0.5，
      整张图会变成"全球沙漠"——降水量的量纲必须由海面饱和来锚定；
    - 陆地降雨 = 背景对流 + 抬升致雨两部分。只留抬升项的话，平坦内陆永不下雨；
    - 背风侧因为水汽已被迎风坡抽走，自然变干（雨影）。
    """
    rows, cols = h.shape
    par = np.clip(h - sea_level, 0.0, None) * (height_scale_m / 1000.0)  # km
    moist = np.zeros(rows, dtype=np.float64)
    out = np.zeros((rows, cols), dtype=np.float64)
    prev = par[:, 0].copy()
    for c in range(cols):
        col = par[:, c]
        water = h[:, c] <= sea_level
        moist = np.where(
            water,
            capacity,
            np.minimum(capacity, moist + evaporation),
        )
        rise = np.maximum(col - prev, 0.0)
        frac = background + (1.0 - background) * (1.0 - np.exp(-orographic * rise))
        loss = moist * frac
        out[:, c] = loss
        moist = np.maximum(moist - loss, 0.0)
        prev = col
    return out / capacity


def precipitation_map(height: np.ndarray, wind_from_deg: float = 270.0,
                      sea_level: float = 0.0, height_scale_m: float = 1000.0,
                      capacity: float = 1.0, evaporation: float = 0.04,
                      orographic: float = 2.5,
                      background: float = 0.02,
                      reference: float = 0.08) -> np.ndarray:
    """降水（0..1 相对值）。

    ``wind_from_deg`` 用气象学口径（风**从**哪个方向来）：270 = 西风，向东吹。
    非基本风向会吸附到最近的 N/E/S/W（返回值里可通过 ``snap_wind`` 查实际用的方向）。

    雨影的成因在模型里是显式的：迎风坡把水汽按抬升量降掉，过脊之后
    ``moist`` 已被抽干，于是背风侧降水显著偏低。
    """
    h = np.asarray(height, dtype=np.float64)
    code, _ = _snap_wind(wind_from_deg)

    if code == "W":                              # 自西向东
        out = _sweep_east(h, sea_level, height_scale_m, capacity, evaporation,
                          orographic, background)
    elif code == "E":                            # 自东向西
        out = _sweep_east(h[:, ::-1], sea_level, height_scale_m, capacity,
                          evaporation, orographic, background)[:, ::-1]
    elif code == "N":                            # 自北向南 == 在转置图上自西向东
        out = _sweep_east(h.T, sea_level, height_scale_m, capacity,
                          evaporation, orographic, background).T
    else:                                        # 自南向北
        out = _sweep_east(h.T[:, ::-1], sea_level, height_scale_m, capacity,
                          evaporation, orographic, background)[:, ::-1].T

    # 归一到"相对降水指数"：逐列降水率 reference（默认 0.08）记为 1.0。
    # 这一步是必要的——原始 out 是"每列降掉水汽的比例"，量级只有 0.02~0.15，
    # 直接拿 0.18/0.40/0.75 这些 Whittaker 阈值去切，会把整张图判成荒漠。
    # reference 越小 → 世界越湿（同一份地形可以按需调）。
    idx = np.clip(out / max(reference, 1e-9), 0.0, 1.0)
    return idx.astype(np.float32)


def classify_biomes_climate(temp_c: np.ndarray, precip: np.ndarray,
                            height: np.ndarray, sea_level: float = 0.0,
                            height_scale_m: float = 1000.0,
                            beach_delta: float = 0.012,
                            alpine_m: float = 3600.0) -> np.ndarray:
    """Whittaker 式 12 类生物群系（按 温度 × 降水，再让高度与水体覆盖）。

    判定顺序：水体 → 海滩 → 高山 → 雪/苔原 → 寒温带（泰加/荒漠）
    → 温带（雨林/森林/草原/荒漠）→ 热带（雨林/稀树草原/沙漠）。
    """
    t = np.asarray(temp_c, dtype=np.float64)
    p = np.asarray(precip, dtype=np.float64)
    h = np.asarray(height, dtype=np.float64)
    alt_m = np.clip(h - sea_level, 0.0, None) * height_scale_m

    out = np.full(h.shape, GRASSLAND, dtype=np.int8)

    tropical = t >= 20.0
    temperate = (t >= 7.0) & (t < 20.0)
    boreal = (t >= 0.0) & (t < 7.0)
    tundra = (t >= -8.0) & (t < 0.0)
    snow = t < -8.0

    # 热带
    out[tropical & (p > 0.70)] = TROPICAL_RAINFOREST
    out[tropical & (p >= 0.30) & (p <= 0.70)] = SAVANNA
    out[tropical & (p < 0.30)] = HOT_DESERT
    # 温带
    out[temperate & (p > 0.75)] = TEMPERATE_RAINFOREST
    out[temperate & (p >= 0.40) & (p <= 0.75)] = TEMPERATE_FOREST
    out[temperate & (p >= 0.18) & (p < 0.40)] = GRASSLAND
    out[temperate & (p < 0.18)] = COLD_DESERT
    # 寒温带
    out[boreal & (p >= 0.25)] = TAIGA
    out[boreal & (p < 0.25)] = COLD_DESERT
    # 极冷
    out[tundra] = TUNDRA
    out[snow] = TUNDRA

    # 高度与水体覆盖（优先级最高）
    out[alt_m >= alpine_m] = ALPINE
    out[h <= sea_level] = WATER
    out[(h > sea_level) & (h <= sea_level + beach_delta)] = BEACH
    return out


def climate_maps(height: np.ndarray, wind_from_deg: float = 270.0,
                 sea_level: float = 0.0, height_scale_m: float = 1000.0,
                 latitude: Optional[np.ndarray] = None,
                 north_up: bool = True) -> dict:
    """一步产出 ``temperature`` / ``precipitation`` / ``biomes`` 与参数快照。"""
    temp = temperature_map(height, latitude=latitude, sea_level=sea_level,
                           height_scale_m=height_scale_m, north_up=north_up)
    precip = precipitation_map(height, wind_from_deg=wind_from_deg,
                               sea_level=sea_level, height_scale_m=height_scale_m)
    biomes = classify_biomes_climate(temp, precip, height, sea_level=sea_level,
                                     height_scale_m=height_scale_m)
    code, snapped = _snap_wind(wind_from_deg)
    return {
        "temperature": temp,
        "precipitation": precip,
        "biomes": biomes,
        "names": dict(CLIMATE_BIOME_NAMES),
        "wind": {"from_deg": float(wind_from_deg), "used": snapped, "code": code},
    }
