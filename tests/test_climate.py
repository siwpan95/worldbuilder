"""气候测试：纬度/高度单调性、雨影方向性、12 类群系判定、老 API 不回归。"""

import numpy as np

from worldbuilder import (
    temperature_map, precipitation_map, classify_biomes_climate,
    climate_maps, CLIMATE_BIOME_NAMES,
    generate_moisture, classify_biomes,
)
from worldbuilder import climate as C


def _ridge(rows=64, cols=64, height=0.9, width=6.0):
    """南北走向的山脊（x 中央），两侧是平原 + 最东/最西是海。"""
    c = np.arange(cols)[None, :].repeat(rows, axis=0).astype(np.float64)
    h = 0.25 + (height - 0.25) * np.exp(-((c - cols / 2.0) / width) ** 2)
    h[:, :4] = 0.05          # 西侧海
    h[:, -4:] = 0.05         # 东侧海
    return h


def test_temperature_equator_to_pole():
    h = np.full((61, 8), 0.0)
    t = temperature_map(h, equator_c=28.0, pole_c=-25.0)
    eq = t[30, 0]           # 中间行 ≈ 赤道
    north = t[0, 0]
    south = t[-1, 0]
    assert abs(float(eq) - 28.0) < 0.6, f"赤道应接近 28，实际 {eq}"
    assert float(north) < -20 and float(south) < -20
    assert t.shape == h.shape


def test_temperature_lapse_with_altitude():
    h = np.zeros((5, 5))
    h[2, 2] = 1.0                    # 1.0 → 1000 m
    t = temperature_map(h, height_scale_m=1000.0, lapse_c_per_km=6.5)
    # 同一行（同纬度）比较，排除纬度带的影响
    assert abs(float(t[2, 0] - t[2, 2]) - 6.5) < 1e-3, "1000 m 应降温 6.5℃"


def test_temperature_north_up_false_flips():
    h = np.zeros((11, 4))
    a = temperature_map(h, north_up=True)
    b = temperature_map(h, north_up=False)
    assert np.allclose(a, b[::-1, :])


def test_precipitation_in_range_and_deterministic():
    h = _ridge()
    p = precipitation_map(h)
    assert p.min() >= 0.0 and p.max() <= 1.0
    assert np.array_equal(p, precipitation_map(h))


def test_rain_shadow_windward_wetter():
    """西风过南北山脊：迎风（西）坡应显著湿于背风（东）坡。"""
    h = _ridge()
    p = precipitation_map(h, wind_from_deg=270.0)
    cols = h.shape[1]
    west_slope = p[:, cols // 2 - 10: cols // 2 - 2].mean()
    east_slope = p[:, cols // 2 + 3: cols // 2 + 11].mean()
    assert west_slope > east_slope * 1.5, (
        f"雨影不成立：迎风 {west_slope:.3f} vs 背风 {east_slope:.3f}"
    )


def test_rain_shadow_flips_with_wind():
    h = _ridge()
    p_east_wind = precipitation_map(h, wind_from_deg=90.0)
    cols = h.shape[1]
    west_slope = p_east_wind[:, cols // 2 - 10: cols // 2 - 2].mean()
    east_slope = p_east_wind[:, cols // 2 + 3: cols // 2 + 11].mean()
    assert east_slope > west_slope * 1.5, "改成东风后，东侧应变成迎风坡"


def test_wind_direction_snapping():
    h = _ridge()
    a = precipitation_map(h, wind_from_deg=260.0)   # 吸附到 270（西风）
    b = precipitation_map(h, wind_from_deg=270.0)
    assert np.allclose(a, b)
    maps = climate_maps(h, wind_from_deg=170.0)
    assert maps["wind"]["used"] == 180.0 and maps["wind"]["code"] == "S"


def test_biome_water_beach_alpine():
    h = np.zeros((40, 40))
    h[:, 20:] = 0.8                                  # 东半陆、西半海
    h[:, 20:22] = 0.008                              # 一条海滩带（< beach_delta 0.012）
    temp = np.full(h.shape, 20.0)
    precip = np.full(h.shape, 0.5)
    b = classify_biomes_climate(temp, precip, h, sea_level=0.0)
    assert np.all(b[:, :19] == C.WATER)
    assert np.all(b[:, 20] == C.BEACH)
    # 0.8 * 1000 m = 800 m，低于高山线 ⇒ 热带（20℃）× 半湿 ⇒ 稀树草原
    assert np.all(b[:, 25:] == C.SAVANNA)

    b2 = classify_biomes_climate(temp, precip, h, sea_level=0.0, height_scale_m=5000.0)
    assert np.all(b2[:, 25:] == C.ALPINE), "0.8 * 5000 m = 4000 m 应判为高山"


def test_biome_temperature_precip_matrix():
    h = np.zeros((2, 1)) + 0.1
    cases = [
        (25.0, 0.85, C.TROPICAL_RAINFOREST),
        (25.0, 0.45, C.SAVANNA),
        (25.0, 0.10, C.HOT_DESERT),
        (15.0, 0.85, C.TEMPERATE_RAINFOREST),
        (15.0, 0.55, C.TEMPERATE_FOREST),
        (15.0, 0.25, C.GRASSLAND),
        (15.0, 0.05, C.COLD_DESERT),
        (3.0, 0.40, C.TAIGA),
        (-4.0, 0.40, C.TUNDRA),
        (-15.0, 0.40, C.TUNDRA),
    ]
    for temp_c, precip, expect in cases:
        b = classify_biomes_climate(np.full((2, 1), temp_c),
                                    np.full((2, 1), precip), h)
        assert int(b[0, 0]) == expect, (
            f"T={temp_c} P={precip} 期望 {CLIMATE_BIOME_NAMES[expect]}，"
            f"实得 {CLIMATE_BIOME_NAMES[int(b[0, 0])]}"
        )


def test_climate_maps_keys():
    m = climate_maps(np.random.RandomState(0).rand(24, 24).astype(np.float32) * 0.6)
    for k in ("temperature", "precipitation", "biomes", "names", "wind"):
        assert k in m
    assert m["temperature"].shape == (24, 24)
    assert m["biomes"].dtype == np.int8
    assert len(m["names"]) == 12


def test_desert_not_at_pole():
    """极地即便降水再少，也应是苔原而不是热带沙漠。"""
    h = np.full((41, 8), 0.1)
    temp = temperature_map(h)                     # 纬度带
    precip = np.full(h.shape, 0.02, dtype=np.float32)   # 极干
    b = classify_biomes_climate(temp, precip, h)
    assert int(b[0, 0]) == C.TUNDRA, "极点行应判为苔原"
    assert int(b[20, 0]) == C.HOT_DESERT, "赤道行干区应为热带沙漠"


def test_legacy_moisture_api_untouched():
    """老的 8 类接口保持原样（另一套编码，不与 12 类混用）。"""
    hm = np.random.RandomState(1).rand(32, 32).astype(np.float32)
    m = generate_moisture(32, 32, seed=3)
    assert m.shape == (32, 32)
    b = classify_biomes(hm, m)
    assert b.shape == (32, 32)
    assert set(np.unique(b)).issubset(set(range(8)))
