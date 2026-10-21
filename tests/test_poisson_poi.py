"""poisson-disk 均匀撒点测试：Bridson 算法的核心不变式是"任意两点间距 >= r"。

这组测试只钉死硬约束：
1. 任意两点欧氏距离 >= r（连续坐标，严格）；
2. 所有点落在采样区域内；
3. 同 seed 逐位可复现；
4. 退化区域（r 过大）也不崩。
并验证它作为 place_pois 补充策略（place_pois_uniform）时落在陆地上。
"""

import numpy as np
import pytest

import worldbuilder as wb
from worldbuilder import poi as P


def _min_pairwise(pts):
    if len(pts) < 2:
        return np.inf
    pts = np.asarray(pts)
    d = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1))
    iu = np.triu_indices(len(pts), 1)
    return float(d[iu].min())


def test_min_distance_enforced():
    # 多个 seed / 多组参数，全部满足 >= r
    for seed in range(6):
        pts = wb.poisson_disk_sample(100.0, 100.0, r=7.0, seed=seed)
        assert _min_pairwise(pts) >= 7.0 - 1e-6, f"seed={seed} 出现小于 r 的间距"


def test_points_in_bounds():
    pts = wb.poisson_disk_sample(50.0, 80.0, r=4.0, seed=1)
    assert pts, "应至少采到一个点"
    for x, y in pts:
        assert 0 <= x < 50.0 and 0 <= y < 80.0


def test_deterministic_per_seed():
    a = wb.poisson_disk_sample(60.0, 60.0, r=5.0, seed=9)
    b = wb.poisson_disk_sample(60.0, 60.0, r=5.0, seed=9)
    assert a == b


def test_different_seed_differs():
    a = wb.poisson_disk_sample(60.0, 60.0, r=5.0, seed=9)
    b = wb.poisson_disk_sample(60.0, 60.0, r=5.0, seed=10)
    assert a != b


def test_large_r_still_returns():
    # r 接近区域尺寸，只会采到极少点，但不应抛异常或死循环
    pts = wb.poisson_disk_sample(20.0, 20.0, r=18.0, seed=2)
    assert isinstance(pts, list)
    assert _min_pairwise(pts) >= 18.0 - 1e-6


def test_bad_args():
    with pytest.raises(ValueError):
        wb.poisson_disk_sample(10.0, 10.0, r=0.0)
    with pytest.raises(ValueError):
        wb.poisson_disk_sample(-1.0, 10.0, r=2.0)


def test_place_pois_uniform_on_land():
    world = wb.generate_world_full(96, 96, seed=7, falloff=0.35)
    land = world["water"] == 0
    pois = wb.place_pois_uniform(world, r=10.0, seed=7)
    assert pois, "96² 世界主陆块上应布到若干点"
    for p in pois:
        r, c = int(p.z), int(p.x)
        assert land[r, c], f"{p.id} 不在陆地上"
    # 同一世界同 seed 可复现
    pois2 = wb.place_pois_uniform(world, r=10.0, seed=7)
    assert [(p.x, p.z, p.kind) for p in pois] == [(p.x, p.z, p.kind) for p in pois2]
