"""WFC 重叠模型测试：重叠模型没有显式瓦片，约束完全由样本局部统计隐式给出。

唯一要钉住的机械判据：
1. 输出中每一个完整落在内部的 N×N 窗，都必定是样本里出现过的某个 N×N 图案
   （这是"相邻图案重叠区一致"的等价表述，也是重叠模型正确性的核心）；
2. 同 seed 逐位可复现；
3. 退化样本（全同值 / 条纹 / 棋盘）能正常生成且性质成立。

注意：重叠 WFC 对"随机高熵样本"可能无解（这是算法固有属性，不是 bug），
所以本文件一律用**保证可铺**的样本（常量 / 条纹 / 棋盘 / 含全零窗的随机样本）
来做断言，避免把"恰好无解"误判成失败。
"""

import numpy as np
import pytest

import worldbuilder as wb


def _all_windows(arr, N, periodic):
    """返回 arr 中所有 N×N 窗的整数元组集合（与 generate_wfc_overlapping 学图案一致）。"""
    H, W = arr.shape
    wins = set()
    if periodic:
        for y in range(H):
            for x in range(W):
                block = arr[np.mod(np.arange(y, y + N), H)][:, np.mod(np.arange(x, x + N), W)]
                wins.add(tuple(int(v) for v in block.ravel()))
    else:
        if H < N or W < N:
            return wins
        for y in range(H - N + 1):
            for x in range(W - N + 1):
                wins.add(tuple(int(v) for v in arr[y:y + N, x:x + N].ravel()))
    return wins


def test_constant_sample_reconstructs():
    sample = np.ones((8, 8), dtype=int)
    out = wb.generate_wfc_overlapping(sample, 3, 10, 10, seed=1)
    assert out.shape == (10, 10)
    assert set(np.unique(out)).issubset({1})
    assert (out == 1).all()


def test_vertical_stripes_window_invariant_nonperiodic():
    # 竖直条纹样本：x%2。N=2 学两个条纹窗，输出必须是竖直条纹（保证可铺）。
    W = 12
    sample = np.zeros((10, W), dtype=int)
    sample[:, 1::2] = 1
    N = 2
    learned = _all_windows(sample, N, periodic=False)
    out = wb.generate_wfc_overlapping(sample, N, 12, 12, seed=2, periodic=False)
    H = 12
    seen = {tuple(int(v) for v in out[y:y + N, x:x + N].ravel())
            for y in range(H - N + 1) for x in range(W - N + 1)}
    assert seen.issubset(learned), f"出现未在样本中的窗：{seen - learned}"
    # 竖直条纹：列奇偶一致
    for x in range(12):
        col = out[:, x]
        assert (col == col[0]).all(), f"第 {x} 列不是纯条纹"


def test_checkerboard_stays_alternating():
    # 棋盘样本：N=2 只学到两种交替 2×2，输出必须严格黑白交替（保证可铺）。
    sample = np.zeros((6, 6), dtype=int)
    sample[1::2, 1::2] = 1
    sample[0::2, 0::2] = 1
    out = wb.generate_wfc_overlapping(sample, 2, 12, 12, seed=3, periodic=True)
    for y in range(12):
        for x in range(12):
            if x + 1 < 12:
                assert out[y, x] != out[y, x + 1], f"({y},{x}) 东西不交替"
            if y + 1 < 12:
                assert out[y, x] != out[y + 1, x], f"({y},{x}) 南北不交替"


def test_values_come_from_sample_domain():
    sample = np.array([[0, 2], [2, 0]], dtype=int)   # 仅含 0 与 2
    out = wb.generate_wfc_overlapping(sample, 2, 8, 8, seed=4, periodic=True)
    assert set(np.unique(out)).issubset({0, 2})


def test_deterministic_per_seed():
    W = 12
    sample = np.zeros((10, W), dtype=int)
    sample[:, 1::2] = 1
    a = wb.generate_wfc_overlapping(sample, 2, 14, 14, seed=5, periodic=False)
    b = wb.generate_wfc_overlapping(sample, 2, 14, 14, seed=5, periodic=False)
    assert np.array_equal(a, b)


def test_seed_sensitivity_and_validity():
    # 含全零窗的随机样本：全零图案保证存在合法铺法（全零场），随机部分提供大量
    # 其它铺法，不同 seed 应探索到不同结果（且都合法）。
    rng = np.random.RandomState(0)
    sample = rng.randint(0, 4, size=(12, 12))
    sample[0:2, 0:2] = 0                       # 强制全零 2×2 窗 → 保证可铺
    N = 2
    learned = _all_windows(sample, N, periodic=True)
    first = wb.generate_wfc_overlapping(sample, N, 16, 16, seed=0)
    # 同 seed 可复现
    again = wb.generate_wfc_overlapping(sample, N, 16, 16, seed=0)
    assert np.array_equal(first, again)
    # 每个完整窗都在学过的集合里（合法性）
    H = 16
    for y in range(H - N + 1):
        for x in range(H - N + 1):
            assert tuple(int(v) for v in first[y:y + N, x:x + N].ravel()) in learned
    # 多个 seed 中至少有两个结果不同（证明 seed 真正起作用）
    outs = {tuple(map(tuple, first))}
    for s in range(1, 8):
        o = wb.generate_wfc_overlapping(sample, N, 16, 16, seed=s)
        outs.add(tuple(map(tuple, o)))
    assert len(outs) >= 2, "多个 seed 应产生不同铺法"


def test_periodic_out_runs():
    sample = np.random.RandomState(11).randint(0, 3, size=(8, 8))
    out = wb.generate_wfc_overlapping(sample, 2, 10, 10, seed=10,
                                      periodic=True, periodic_out=True)
    assert out.shape == (10, 10)


def test_bad_args():
    with pytest.raises(ValueError):
        wb.generate_wfc_overlapping(np.ones((4, 4), dtype=int), 0, 4, 4)
    with pytest.raises(ValueError):
        wb.generate_wfc_overlapping(np.ones((4, 4), dtype=int), 2, 0, 4)
