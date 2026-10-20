"""worldbuilder「噪声 v2」测试：向后兼容黄金值 + warp / ridged / cellular 新 API。

运行方式（仓库根目录）：
    python -m pytest tests/ -q          # 推荐
    python tests/test_noise_v2.py       # 没有 pytest 时自跑（失败返回码 1）

兼容性部分的黄金值由**改动前**的实现（git HEAD 的 worldbuilder/noise.py）在本机
numpy 2.5.4 上算出，全部按 17 位有效数字（repr 往返）硬编码。比较方式是
``tobytes()``——真正的逐位相等，连 -0.0/NaN 位模式都算在内。
注意：cos/sin 依赖底层 libm/SIMD 实现，换 numpy 版本或换 CPU 架构（AVX512 等）
时黄金值可能不再逐位相同；届时请用 HEAD 版本重新生成，而不是放宽断言。
"""
import os
import sys

import numpy as np

# 允许 `python tests/test_noise_v2.py` 直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import worldbuilder as wb


# ---------------------------------------------------------------- 固定采样格
GRID_X = [0.1, 1.7, 3.3, 5.9]
GRID_Y = [0.2, 2.4, 4.6, 6.8]


def _grid():
    """4x4 固定采样格（meshgrid 默认 'xy'）。"""
    X, Y = np.meshgrid(GRID_X, GRID_Y)
    return X, Y


# ---------------------------------------------------------------- 黄金值（旧实现）
GOLD_VALUE = [  # value_noise(X, Y)
    [0.09724174890961954, 0.10566063827338659, 0.46922725389652487, 0.6310236639863325],
    [0.607354964856369, 0.6330657368492679, 0.7132967780276617, 0.6764183544272645],
    [0.12108967877286761, 0.7515666692772277, 0.3043344592013127, 0.6649388822149984],
    [0.6255005045304877, 0.8549903247144586, 0.6737990294596288, 0.3855129840975595],
]

GOLD_PERLIN = [  # perlin_noise(X, Y)
    [0.5679518433847227, 0.5584004149135119, 0.33644145779822565, 0.3693733862919557],
    [0.42099770478989434, 0.6270578283623424, 0.6177715258695753, 0.2634511041342839],
    [0.6581610563824863, 0.2842444578243422, 0.43998773412017195, 0.4754368852793534],
    [0.6413063127084779, 0.33913978695558084, 0.6611006185276015, 0.37607406935817866],
]

GOLD_FBM = [  # fbm(X, Y)
    [0.5120210328392267, 0.6277827707212594, 0.4355735687751572, 0.45517528926736867],
    [0.46602189375409997, 0.484509909634181, 0.6137296857021333, 0.37580977386050113],
    [0.545093998436141, 0.33130397431223657, 0.514652832382755, 0.42740118757577567],
    [0.5799399694090873, 0.45165835704522406, 0.48178989337714195, 0.4543829178101614],
]

GOLD_FRACTAL = [  # fractal_noise(X, Y)
    [0.5120210328392267, 0.6277827707212594, 0.4355735687751572, 0.45517528926736867],
    [0.46602189375409997, 0.484509909634181, 0.6137296857021333, 0.37580977386050113],
    [0.545093998436141, 0.33130397431223657, 0.514652832382755, 0.42740118757577567],
    [0.5799399694090873, 0.45165835704522406, 0.48178989337714195, 0.4543829178101614],
]

GOLD_SIMPLEX = [  # simplex_noise(X, Y)
    [0.9265013096439538, 0.09103507252526105, 0.27523552067724555, 0.44492213521997537],
    [0.4245020958326661, 0.6792336615510616, 0.6712476961074061, 0.4133936528236005],
    [0.6926900912233838, 0.3431556112763216, 0.22254982885235064, 0.5532340739065884],
    [0.373164637728607, 0.5569883062447024, 0.4972836427479031, 0.5029161644539579],
]

GOLD_FBM_TUNED = [  # fbm(X, Y, octaves=6, lacunarity=2.3, gain=0.47, seed=9)
    [0.4432012983681378, 0.3871265183240987, 0.558106725120341, 0.5056150615496801],
    [0.5988070708788367, 0.4008695185334162, 0.48335078761409767, 0.5590100869102699],
    [0.35845335947312246, 0.3377792790576327, 0.516062931558853, 0.42007389276780444],
    [0.48067422096030976, 0.36777828166042725, 0.4553674773299856, 0.5086397355044817],
]

GOLD_PERLIN_SEED = [  # perlin_noise(X, Y, seed=42)
    [0.6057028084426501, 0.43906312987114576, 0.501043259776137, 0.39630159923635144],
    [0.5256427509160583, 0.32970674355531726, 0.1943184043226981, 0.7783103586198769],
    [0.3564741128720732, 0.4596224384214083, 0.5685047743426375, 0.5071606065669271],
    [0.521265455734123, 0.586400781203179, 0.36396692240554046, 0.39829207144945517],
]

# 标量输入：value_noise(1.5, 2.5) / perlin_noise(0.25, 0.75, seed=2) /
# fbm(-3.5, 4.25, seed=3) / fractal_noise(7.75, -2.0, octaves=3, seed=4) /
# simplex_noise(-3.5, 4.25, seed=5)
GOLD_SCALAR_VALUE = 0.6916974489305622
GOLD_SCALAR_PERLIN = 0.30846834659775924
GOLD_SCALAR_FBM = 0.5298750055192375
GOLD_SCALAR_FRACTAL = 0.3666303700307207
GOLD_SCALAR_SIMPLEX = 0.7454914494036895


# ---------------------------------------------------------------- 工具
def _assert_bit_identical(got, gold, label):
    """严格逐位相等（含 dtype / shape）。"""
    gold = np.asarray(gold, dtype=np.float64)
    got = np.asarray(got)
    assert got.shape == gold.shape, "%s: 形状 %r != %r" % (label, got.shape, gold.shape)
    assert got.dtype == np.float64, "%s: dtype %r 不是 float64" % (label, got.dtype)
    if got.tobytes() != gold.tobytes():
        diff = np.max(np.abs(got - gold))
        raise AssertionError("%s: 与旧实现不逐位相等，最大偏差 %.3e" % (label, diff))


def _assert_unit_range(a, label):
    a = np.asarray(a, dtype=np.float64)
    assert np.all(np.isfinite(a)), "%s: 出现非有限值" % label
    assert float(a.min()) >= 0.0, "%s: 最小值 %.6f < 0" % (label, float(a.min()))
    assert float(a.max()) <= 1.0, "%s: 最大值 %.6f > 1" % (label, float(a.max()))


def _smooth_grid(n=64, span=12.0):
    xs = np.linspace(0.0, span, n)
    return np.meshgrid(xs, xs)


def _roughness(a):
    """相邻像素平均差 / 标准差：衡量画面是否被撕成噪点。"""
    return float(np.mean(np.abs(np.diff(a, axis=1))) / a.std())


# ---------------------------------------------------------------- 兼容性（旧 API）
def test_compat_value_noise():
    X, Y = _grid()
    _assert_bit_identical(wb.value_noise(X, Y), GOLD_VALUE, "value_noise(X, Y)")


def test_compat_perlin_noise():
    X, Y = _grid()
    _assert_bit_identical(wb.perlin_noise(X, Y), GOLD_PERLIN, "perlin_noise(X, Y)")


def test_compat_fbm_and_fractal_noise():
    X, Y = _grid()
    _assert_bit_identical(wb.fbm(X, Y), GOLD_FBM, "fbm(X, Y)")
    _assert_bit_identical(wb.fractal_noise(X, Y), GOLD_FRACTAL, "fractal_noise(X, Y)")


def test_compat_simplex_noise():
    X, Y = _grid()
    _assert_bit_identical(wb.simplex_noise(X, Y), GOLD_SIMPLEX, "simplex_noise(X, Y)")


def test_compat_legacy_non_default_params():
    """老参数（octaves/lacunarity/gain/seed）语义未被改动。"""
    X, Y = _grid()
    _assert_bit_identical(
        wb.fbm(X, Y, octaves=6, lacunarity=2.3, gain=0.47, seed=9),
        GOLD_FBM_TUNED, "fbm(octaves=6, lacunarity=2.3, gain=0.47, seed=9)")
    _assert_bit_identical(wb.perlin_noise(X, Y, seed=42),
                          GOLD_PERLIN_SEED, "perlin_noise(seed=42)")


def test_compat_scalar_inputs():
    """标量输入的老行为（0 维返回、float64）也逐位不变。"""
    pairs = [
        (wb.value_noise(1.5, 2.5), GOLD_SCALAR_VALUE, "value_noise(1.5, 2.5)"),
        (wb.perlin_noise(0.25, 0.75, seed=2), GOLD_SCALAR_PERLIN, "perlin_noise(0.25, 0.75, 2)"),
        (wb.fbm(-3.5, 4.25, seed=3), GOLD_SCALAR_FBM, "fbm(-3.5, 4.25, 3)"),
        (wb.fractal_noise(7.75, -2.0, octaves=3, seed=4), GOLD_SCALAR_FRACTAL,
         "fractal_noise(7.75, -2.0, 3, 4)"),
        (wb.simplex_noise(-3.5, 4.25, seed=5), GOLD_SCALAR_SIMPLEX, "simplex_noise(-3.5, 4.25, 5)"),
    ]
    for got, gold, label in pairs:
        assert np.ndim(got) == 0, "%s: 标量输入未返回 0 维" % label
        assert np.asarray(got).dtype == np.float64, "%s: dtype 不是 float64" % label
        assert float(got) == gold, "%s: %.17g != %.17g" % (label, float(got), gold)


# ---------------------------------------------------------------- warp_noise
def test_warp_zero_strength_equals_direct_base():
    """warp_strength=0 必须等价于基噪声直采（逐位）。"""
    X, Y = _smooth_grid(48)
    cases = {
        "fbm": lambda x, y, s: wb.fbm(x, y, seed=s),
        "fractal": lambda x, y, s: wb.fractal_noise(x, y, seed=s),
        "perlin": lambda x, y, s: wb.perlin_noise(x, y, seed=s),
        "value": lambda x, y, s: wb.value_noise(x, y, seed=s),
        "simplex": lambda x, y, s: wb.simplex_noise(x, y, seed=s),
    }
    for base, direct in cases.items():
        for seed in (0, 7):
            got = wb.warp_noise(X, Y, seed=seed, warp_strength=0.0, base=base)
            want = direct(X, Y, seed)
            assert got.tobytes() == np.asarray(want, dtype=np.float64).tobytes(), \
                "warp_strength=0 与 base=%r（seed=%d）直采不逐位相等" % (base, seed)


def test_warp_actually_warps_and_stays_smooth():
    X, Y = _smooth_grid(64)
    base = wb.fbm(X, Y, seed=3)
    warped = wb.warp_noise(X, Y, seed=3, warp_strength=1.0)
    _assert_unit_range(warped, "warp_noise")
    assert not np.allclose(warped, base, atol=1e-3), "warp_strength>0 却没有产生偏移"
    # 偏移量必须缩放得当：扭曲后画面的粗糙度与 fbm 同量级，不能变成噪点
    assert _roughness(warped) < 3.0 * _roughness(base), "扭曲后出现噪点化（粗糙度过高）"
    # 两个分量都要起作用：只给 dx 会退化成条带
    dx_only = wb.fbm(X + (wb.perlin_noise(X * 0.5, Y * 0.5, seed=1013) * 2 - 1),
                     Y, seed=3)
    assert not np.allclose(warped, dx_only, atol=1e-6)


def test_warp_rejects_unknown_base():
    try:
        wb.warp_noise(0.5, 0.5, base="perling")
    except ValueError:
        return
    raise AssertionError("未知 base 未抛 ValueError")


# ---------------------------------------------------------------- ridged_noise
def test_ridged_range_and_variance():
    X, Y = _smooth_grid(64)
    a = wb.ridged_noise(X, Y, seed=5)
    _assert_unit_range(a, "ridged_noise")
    assert float(a.std()) > 1e-3, "ridged_noise 输出近似常数（std=%.3e）" % float(a.std())
    assert a.dtype == np.float64 and a.shape == X.shape


def test_ridged_sharpness_and_octaves():
    X, Y = _smooth_grid(48)
    soft = wb.ridged_noise(X, Y, seed=2, sharpness=1.0)
    hard = wb.ridged_noise(X, Y, seed=2, sharpness=4.0)
    _assert_unit_range(soft, "ridged(sharpness=1)")
    _assert_unit_range(hard, "ridged(sharpness=4)")
    # r∈[0,1] 时 r^4 <= r，故均值单调下降
    assert float(hard.mean()) < float(soft.mean()), "sharpness 未加深脊（均值未下降）"
    assert not np.allclose(soft, hard), "sharpness 未生效"
    more = wb.ridged_noise(X, Y, seed=2, octaves=6)
    assert not np.allclose(more, wb.ridged_noise(X, Y, seed=2)), "octaves 未生效"


def test_ridged_rejects_bad_args():
    for kwargs in ({"octaves": 0}, {"sharpness": 0.0}, {"sharpness": -1.0}):
        try:
            wb.ridged_noise(0.3, 0.4, **kwargs)
        except ValueError:
            continue
        raise AssertionError("ridged_noise(%r) 未抛 ValueError" % kwargs)


# ---------------------------------------------------------------- cellular_noise
def test_cellular_types_range_and_relations():
    X, Y = _smooth_grid(64)
    f1 = wb.cellular_noise(X, Y, seed=4, return_type="f1")
    f2 = wb.cellular_noise(X, Y, seed=4, return_type="f2")
    f2f1 = wb.cellular_noise(X, Y, seed=4, return_type="f2f1")
    for name, a in (("f1", f1), ("f2", f2), ("f2f1", f2f1)):
        _assert_unit_range(a, "cellular_noise(%s)" % name)
        assert a.dtype == np.float64 and a.shape == X.shape
        assert float(a.std()) > 1e-3, "cellular_noise(%s) 近似常数" % name
    # 三者共用同一归一化尺度，故归一化后仍保持 f1<=f2、f2-f1>=0
    assert np.all(f1 <= f2), "存在 f1 > f2 的像素"
    assert np.all(f2f1 >= 0.0), "存在 f2f1 < 0 的像素"
    # 细胞边界必须真的存在
    assert float(f2f1.min()) < 0.05, "f2f1 没有趋近 0 的边界像素"


def test_cellular_regular_lattice_when_jitter_zero():
    """jitter=0：特征点固定在格角，(0.5,0.5) 到最近格角 √0.5，归一化后恰为 0.5。"""
    assert abs(float(wb.cellular_noise(0.5, 0.5, seed=0, jitter=0.0)) - 0.5) < 1e-12
    # 四个角点等距 -> f1 == f2 -> f2f1 == 0
    assert abs(float(wb.cellular_noise(0.5, 0.5, seed=0, jitter=0.0,
                                      return_type="f2f1"))) < 1e-12
    # 无抖动时场按 1 格周期重复（特征点与 cell 索引一一对应）
    xs = np.array([0.13, 0.37, 0.61, 0.88])
    ys = np.array([0.21, 0.44, 0.72, 0.95])
    a = wb.cellular_noise(xs, ys, seed=9, jitter=0.0)
    b = wb.cellular_noise(xs + 3.0, ys - 2.0, seed=9, jitter=0.0)
    assert np.allclose(a, b, atol=1e-12), "jitter=0 时细胞场不具格点周期性"


def test_cellular_jitter_changes_lattice():
    X, Y = _smooth_grid(48)
    a = wb.cellular_noise(X, Y, seed=6, jitter=0.0)
    b = wb.cellular_noise(X, Y, seed=6, jitter=1.0)
    _assert_unit_range(b, "cellular(jitter=1)")
    assert not np.allclose(a, b), "jitter 未生效"


def test_cellular_rejects_bad_args():
    for kwargs in ({"jitter": -0.1}, {"jitter": 1.5}, {"return_type": "f3"}):
        try:
            wb.cellular_noise(0.3, 0.4, **kwargs)
        except ValueError:
            continue
        raise AssertionError("cellular_noise(%r) 未抛 ValueError" % kwargs)


# ---------------------------------------------------------------- 通用行为
def test_seed_reproducible_and_distinct():
    X, Y = _smooth_grid(32)
    calls = [
        ("warp_noise", lambda s: wb.warp_noise(X, Y, seed=s)),
        ("ridged_noise", lambda s: wb.ridged_noise(X, Y, seed=s)),
        ("cellular_noise", lambda s: wb.cellular_noise(X, Y, seed=s)),
        ("cellular_noise/f2f1", lambda s: wb.cellular_noise(X, Y, seed=s, return_type="f2f1")),
    ]
    for name, fn in calls:
        a, b, c = fn(11), fn(11), fn(12)
        assert a.tobytes() == b.tobytes(), "%s: 同 seed 两次结果不同" % name
        assert a.tobytes() != c.tobytes(), "%s: 不同 seed 结果相同" % name


def test_scalar_input_returns_zero_dim():
    for name, fn in (
        ("warp_noise", lambda: wb.warp_noise(1.5, 2.5, seed=1)),
        ("ridged_noise", lambda: wb.ridged_noise(1.5, 2.5, seed=1)),
        ("cellular_noise", lambda: wb.cellular_noise(1.5, 2.5, seed=1)),
    ):
        v = fn()
        assert np.ndim(v) == 0, "%s: 标量输入未返回 0 维（shape=%r）" % (name, np.shape(v))
        assert np.asarray(v).dtype == np.float64, "%s: dtype 不是 float64" % name
        assert 0.0 <= float(v) <= 1.0, "%s: 标量输出越界" % name


def test_array_shape_preserved_and_broadcasting():
    X, Y = _smooth_grid(16)
    for name, fn in (
        ("warp_noise", wb.warp_noise),
        ("ridged_noise", wb.ridged_noise),
        ("cellular_noise", wb.cellular_noise),
    ):
        out = fn(X, Y)
        assert out.shape == X.shape, "%s: 形状 %r != %r" % (name, out.shape, X.shape)
        _assert_unit_range(out, name)
        # 可广播输入：(1,4) 与 (3,1) -> (3,4)
        b = fn(np.zeros((1, 4)), np.zeros((3, 1)))
        assert b.shape == (3, 4), "%s: 广播形状 %r != (3, 4)" % (name, b.shape)
        # 整数输入也应可用
        i = fn(np.arange(4), np.arange(4))
        assert i.shape == (4,)
        _assert_unit_range(i, name + "(int 输入)")


def test_new_functions_exported():
    for name in ("warp_noise", "ridged_noise", "cellular_noise"):
        assert name in wb.__all__, "%s 未加入 __all__" % name
        assert callable(getattr(wb, name)), "%s 未从包根导出" % name


# ---------------------------------------------------------------- 自跑入口
def _main():
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print("PASS  %s" % name)
        except AssertionError as exc:
            failed.append(name)
            print("FAIL  %s\n      %s" % (name, exc))
    print("\n%d passed, %d failed / %d total" % (len(tests) - len(failed), len(failed), len(tests)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_main())
