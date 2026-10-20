# -*- coding: utf-8 -*-
"""road.py 冒烟测试：python test_road.py（无 pytest 依赖，与 test_smoke.py 同风格）。"""
import numpy as np

from worldbuilder.road import gobi_corridor, sample_height, smoothstep


def main():
    # 1) 走廊形状：z=0 处必须是 corridor_level，远处更高
    hm, xs, zs = gobi_corridor(seed=244)
    mid_r = np.argmin(np.abs(zs))          # z≈0 的行
    mid_c = len(xs) // 2
    assert abs(hm[mid_r, mid_c] - 0.30) < 1e-5, f'走廊中心应压平: {hm[mid_r, mid_c]}'
    # 走廊带内（|z| < road_half）整行都是 0.30
    assert np.allclose(hm[mid_r, :], 0.30, atol=1e-5), '走廊整行应等高'
    # 远处应明显高于走廊（脊形噪声有随机性，取 >0.5 的保守下限）
    assert hm[2, mid_c] > 0.5, f'远山应隆起: {hm[2, mid_c]}'

    # 2) 连续性：走廊边缘 smoothstep 过渡，无跳变（相邻行差 < 0.15）
    edge_r = np.argmin(np.abs(zs - 3.5))
    diffs = np.abs(np.diff(hm[edge_r - 2:edge_r + 3, :], axis=0))
    assert diffs.max() < 0.15, f'走廊过渡应平滑: max diff {diffs.max()}'

    # 3) 确定性：同 seed 同结果
    hm2, _, _ = gobi_corridor(seed=244)
    assert np.array_equal(hm, hm2), '同 seed 必须逐位相同'

    # 4) 采样：走廊中心采样 = corridor_level * height
    y = sample_height(hm, 0.0, 0.0, extent=40.0, height=7.0)
    assert abs(y - 2.1) < 0.01, f'路面高程应 2.1: {y}'
    # 采样与直接取格点一致
    y2 = sample_height(hm, xs[10], zs[10], extent=40.0, height=7.0)
    assert abs(y2 - hm[10, 10] * 7.0) < 1e-4, '格点采样应精确命中'

    # 5) smoothstep 端点
    assert smoothstep(0.0) == 0.0 and smoothstep(1.0) == 1.0

    print('ok: road.py 走廊压平/平滑/确定性/采样 5 组断言全过')


if __name__ == '__main__':
    main()
