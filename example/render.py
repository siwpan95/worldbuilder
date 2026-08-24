"""render.py —— 把 procgen 生成的数值数据渲染成可视 PNG。

本模块不直接调用 procgen，只负责“数值 -> 图片/文本”的呈现，
便于 run.py 复用。所有渲染均为纯 numpy + Pillow，不依赖 procgen。

约定：
  - 地图类网格（dungeon / cave）：0=墙 1=地
  - 地形/生物群系：int 编码 + 调色板
  - 高度图/噪声：0..1 灰度
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# 每张小格的像素边长（地图放大，便于肉眼查看）
CELL = 12

# 生物群系调色板 (R, G, B)
BIOME_PALETTE = {
    0: (40, 90, 170),    # WATER   水
    1: (210, 200, 140),  # BEACH   滩
    2: (110, 180, 90),   # GRASS   草
    3: (40, 120, 60),    # FOREST  林
    4: (210, 180, 110),  # DESERT  漠
    5: (150, 170, 160),  # TUNDRA  苔
    6: (130, 120, 120),  # MOUNTAIN山
    7: (240, 245, 250),  # SNOW    雪
}

# 地形调色板（heightmap 分类版）
TERRAIN_PALETTE = {
    0: (40, 90, 170),    # WATER
    1: (210, 200, 140),  # SAND
    2: (110, 180, 90),   # GRASS
    3: (40, 120, 60),    # FOREST
    4: (130, 120, 120),  # MOUNTAIN
}


def grid_to_png(grid: np.ndarray, cell: int = CELL,
                wall_color=(20, 20, 28), floor_color=(225, 222, 210)) -> Image.Image:
    """0=墙 1=地 的网格 -> PNG。"""
    grid = np.asarray(grid)
    h, w = grid.shape
    img = Image.new("RGB", (w * cell, h * cell), wall_color)
    px = img.load()
    for y in range(h):
        for x in range(w):
            if grid[y, x]:
                for dy in range(cell):
                    for dx in range(cell):
                        px[x * cell + dx, y * cell + dy] = floor_color
    return img


def classes_to_png(classes: np.ndarray, palette: dict,
                   cell: int = CELL) -> Image.Image:
    """int 编码的类别数组 -> 调色板 PNG。"""
    classes = np.asarray(classes)
    h, w = classes.shape
    img = Image.new("RGB", (w * cell, h * cell))
    px = img.load()
    for y in range(h):
        for x in range(w):
            col = palette.get(int(classes[y, x]), (0, 0, 0))
            for dy in range(cell):
                for dx in range(cell):
                    px[x * cell + dx, y * cell + dy] = col
    return img


def gray_to_png(arr: np.ndarray, cell: int = CELL) -> Image.Image:
    """0..1 的灰度数组 -> 放大 PNG。"""
    a = np.clip(np.asarray(arr, dtype=np.float64), 0.0, 1.0)
    h, w = a.shape
    img = Image.new("RGB", (w * cell, h * cell))
    px = img.load()
    for y in range(h):
        for x in range(w):
            v = int(a[y, x] * 255)
            for dy in range(cell):
                for dx in range(cell):
                    px[x * cell + dx, y * cell + dy] = (v, v, v)
    return img


def _fit_font(size: int):
    """尽量取一个等宽字体，失败则退回 PIL 默认。"""
    for path in ("consola.ttf", "cour.ttf", "DejaVuSansMono.ttf",
                 "Courier New.ttf", "simsun.ttc"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def grid_to_ascii_png(grid: np.ndarray, cell: int = 14,
                      wall: str = "#", floor: str = ".",
                      fg=(220, 220, 220), bg=(18, 18, 24)) -> Image.Image:
    """网格 -> 等宽 ASCII 字符 PNG（便于保存可读地图）。"""
    g = np.asarray(grid)
    h, w = g.shape
    font = _fit_font(cell - 2)
    char_w, char_h = cell, cell
    img = Image.new("RGB", (w * char_w, h * char_h), bg)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        for x in range(w):
            ch = floor if g[y, x] else wall
            draw.text((x * char_w, y * char_h), ch, fill=fg, font=font)
    return img


def add_legend(path: str, title: str, items: list[tuple[str, tuple]]):
    """在已存 PNG 右侧追加图例（标题 + 色块条目），覆盖写回 path。"""
    img = Image.open(path).convert("RGB")
    lw = 150
    new = Image.new("RGB", (img.width + lw, max(img.height, 28 + len(items) * 22 + 10)),
                    (255, 255, 255))
    new.paste(img, (0, 0))
    draw = ImageDraw.Draw(new)
    font = _fit_font(14)
    draw.text((img.width + 8, 6), title, fill=(0, 0, 0), font=font)
    for i, (label, color) in enumerate(items):
        y = 28 + i * 22
        draw.rectangle([img.width + 8, y, img.width + 28, y + 16], fill=color)
        draw.text((img.width + 34, y), label, fill=(0, 0, 0), font=font)
    new.save(path)


# ---------------------------------------------------------------------------
# 城镇（矢量 -> PNG）
# ---------------------------------------------------------------------------
def town_to_png(town: dict, scale_to: int = 900, margin: int = 24) -> Image.Image:
    """把 generate_town 的城镇渲染成 PNG（带城墙/路网/建筑/ward 配色）。"""
    minx, miny, maxx, maxy = town["bounds"]
    W = max(maxx - minx, 1e-6)
    H = max(maxy - miny, 1e-6)
    scale = scale_to / max(W, H)

    img_w = int(W * scale) + 2 * margin
    img_h = int(H * scale) + 2 * margin
    paper = (232, 226, 210)
    img = Image.new("RGB", (img_w, img_h), paper)
    draw = ImageDraw.Draw(img)

    def tp(p):
        return (int((p.x - minx) * scale) + margin,
                int((maxy - p.y) * scale) + margin)

    road_w = max(2, int(2.0 * scale))  # 主街宽

    # 1) ward 地块填充
    for w in town["wards"]:
        pts = [tp(v) for v in w["polygon"].verts]
        if len(pts) >= 3:
            draw.polygon(pts, fill=w["color"])

    # 2) 建筑（地块内更小多边形，填充更深色并描边）
    for w in town["wards"]:
        dark = tuple(max(0, c - 55) for c in w["color"])
        for b in w["buildings"]:
            pts = [tp(v) for v in b.verts]
            if len(pts) >= 3:
                draw.polygon(pts, fill=dark, outline=(92, 82, 72))

    # 3) 路网（城门 -> 中心 的折线，用纸色“切”出街道）
    for s in town["streets"]:
        pts = [tp(p) for p in s]
        if len(pts) >= 2:
            draw.line(pts, fill=paper, width=road_w)

    # 4) 城墙（描边 + 塔楼）
    wall = town["wall"]
    if wall:
        wpts = [tp(v) for v in wall["shape"].verts]
        if len(wpts) >= 3:
            draw.polygon(wpts, outline=(58, 52, 46), width=max(2, int(2.0 * scale)))
        r = max(3, int(1.6 * scale))
        for t in wall["towers"]:
            x, y = tp(t)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(58, 52, 46))
        # 城门：在城墙上画浅色缺口标记
        for g in wall["gates"]:
            x, y = tp(g)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(200, 190, 170))

    return img
