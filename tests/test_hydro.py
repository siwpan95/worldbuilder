"""水文测试：填洼不变量 / D8 方向 / 汇水守恒 / 河流收尾 / 湖泊与海岸。

口径：不依赖 pytest 之外的库；断言用 assert，便于 `python tests/test_hydro.py` 自跑。
"""

import numpy as np

from worldbuilder import (
    fill_depressions, flow_directions, flow_accumulation,
    extract_rivers, lakes, coastline, hydrology, river_width,
)


def _bowl(rows=40, cols=40, depth=0.35):
    """圆碗：中间一个封闭洼地（没有出口）。"""
    r = np.linspace(-1, 1, rows)[:, None]
    c = np.linspace(-1, 1, cols)[None, :]
    d = np.sqrt(r ** 2 + c ** 2)
    return (0.8 - depth * np.clip(1.0 - d, 0.0, 1.0)).astype(np.float64)


def _east_plane(rows=16, cols=24):
    """自西向东均匀下降的斜面（每格降 0.01）。"""
    return (0.9 - 0.01 * np.arange(cols)[None, :].repeat(rows, axis=0)).astype(np.float64)


def _valley(rows=48, cols=48):
    """南向倾斜 + 中央沟槽：应形成 1 条主干河。"""
    r = np.arange(rows)[:, None].astype(np.float64)
    c = np.arange(cols)[:, None].astype(np.float64).T
    groove = 0.35 * np.exp(-((c - cols / 2.0) / 2.5) ** 2)
    return 0.95 - 0.008 * r - groove


def test_fill_depressions_never_lowers():
    h = _bowl()
    f = fill_depressions(h)
    assert f.shape == h.shape
    assert np.all(f >= h - 1e-12), "填洼只能抬高，不能降低任何格"
    assert f[20, 20] > h[20, 20] + 0.05, "碗底应被明显抬高"


def test_fill_depressions_leaves_no_interior_pit():
    """填完之后，任何内部格都必须有一个严格更低的邻居（否则水还是出不去）。"""
    f = fill_depressions(_bowl())
    rows, cols = f.shape
    inner = f[1:-1, 1:-1]
    lower = np.minimum.reduce([
        f[:-2, 1:-1], f[2:, 1:-1], f[1:-1, :-2], f[1:-1, 2:],
    ])
    assert np.all(inner > lower), "存在内部洼地：仍有格子四邻都不低于自己"


def test_fill_depressions_idempotent_and_keeps_border():
    h = _bowl()
    f1 = fill_depressions(h)
    f2 = fill_depressions(f1)
    assert np.allclose(f1, f2), "对已填平的地形再填一次应不变"
    assert np.allclose(f1[0, :], h[0, :]), "边界是出水口，高度必须保持"


def test_flow_directions_point_downhill():
    f = fill_depressions(_bowl())
    d = flow_directions(f)
    rows, cols = f.shape
    offs = [(0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1)]
    checked = 0
    for r in range(rows):
        for c in range(cols):
            k = int(d[r, c])
            if k < 0:
                continue
            dy, dx = offs[k]
            assert f[r + dy, c + dx] < f[r, c], f"({r},{c}) 的流向不是下降方向"
            checked += 1
    assert checked > 0.5 * f.size, "绝大多数格都该有下游"


def test_flow_accumulation_conserves_cells():
    """纯东向斜面上：第 c 列累积 = c+1，总和可闭式验证。"""
    h = _east_plane(rows=6, cols=8)
    d = flow_directions(h)
    acc = flow_accumulation(h, d)
    expected = 6 * (8 * 9 / 2)
    assert abs(acc.sum() - expected) < 1e-6, f"{acc.sum()} != {expected}"
    assert np.allclose(acc[:, 0], 1.0), "最西列只有自身"
    assert np.allclose(acc[:, -1], 8.0), "最东列承接整行"


def test_flow_accumulation_monotone_downstream():
    f = fill_depressions(_valley())
    d = flow_directions(f)
    acc = flow_accumulation(f, d)
    rows, cols = f.shape
    offs = [(0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1)]
    for r in range(rows):
        for c in range(cols):
            k = int(d[r, c])
            if k < 0:
                continue
            dy, dx = offs[k]
            assert acc[r + dy, c + dx] >= acc[r, c]


def test_rivers_exist_and_end_somewhere():
    f = fill_depressions(_valley())
    d = flow_directions(f)
    acc = flow_accumulation(f, d)
    rivers = extract_rivers(f, acc, d, threshold=40.0)
    assert rivers, "沟槽地形应至少抽出一条河"
    rows, cols = f.shape
    offs = [(0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1)]
    for rv in rivers:
        assert len(rv["points"]) >= 4
        x, y = rv["points"][-1]
        xi, yi = int(x), int(y)
        at_border = x in (0, cols - 1) or y in (0, rows - 1)
        ends_in_sink = d[yi, xi] < 0
        # 第三种合法收尾：汇入另一条已走过的河（汇流点），此时下游汇水更大
        merged = False
        k = int(d[yi, xi])
        if k >= 0:
            dy, dx = offs[k]
            merged = acc[yi + dy, xi + dx] > acc[yi, xi]
        assert at_border or ends_in_sink or merged, (
            f"河流末点 ({x},{y}) 既不在边界、不是汇、也不是汇流点"
        )
        assert rv["acc_max"] >= 40.0
        assert rv["length"] > 0


def test_rivers_respect_threshold():
    f = fill_depressions(_valley())
    d = flow_directions(f)
    acc = flow_accumulation(f, d)
    few = extract_rivers(f, acc, d, threshold=10_000.0)
    assert few == [], "阈值高于总格数时不应有成河"


def test_lakes_detected_in_bowl():
    h = _bowl()
    f = fill_depressions(h)
    info = lakes(h, f)
    assert info["count"] >= 1
    assert info["mask"].any()
    lake = info["lakes"][0]
    assert lake["area"] >= 4
    assert lake["surface"] > h[20, 20]


def test_no_lakes_on_plane():
    h = _east_plane()
    f = fill_depressions(h)
    assert lakes(h, f)["count"] == 0, "斜面没有洼地，不该有湖"


def test_coastline_only_on_land_next_to_water():
    h = np.zeros((10, 10))
    h[:, 5:] = 0.5                      # 右半边是陆地
    coast = coastline(h, sea_level=0.1)
    assert np.all(coast[:, 5]), "land 的第一列（贴着水）应全是海岸"
    assert not coast[:, 6:].any(), "陆地内部不该判成海岸"


def test_river_width_power_law():
    w = river_width(np.array([1.0, 100.0, 10000.0]))
    assert w[0] <= w[1] <= w[2]
    assert abs(float(w[1]) - 10.0) < 1e-3          # 100 ** 0.5
    assert abs(float(w[2]) - 100.0) < 1e-3


def test_hydrology_bundle_shapes():
    h = _valley()
    out = hydrology(h, sea_level=0.0)
    for key in ("filled", "dirs", "acc", "rivers", "lakes", "coast", "river_mask", "width"):
        assert key in out
    assert out["filled"].shape == h.shape
    assert out["dirs"].shape == h.shape
    assert out["acc"].shape == h.shape
    assert out["width"].shape == h.shape
    assert isinstance(out["rivers"], list)


def test_hydrology_is_deterministic():
    a = hydrology(_valley())["acc"]
    b = hydrology(_valley())["acc"]
    assert np.array_equal(a, b), "同输入两次必须逐位一致"
