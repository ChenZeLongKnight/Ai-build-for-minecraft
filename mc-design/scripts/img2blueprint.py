# -*- coding: utf-8 -*-
"""
img2blueprint.py — 图片 → Minecraft 蓝图 JSON（直接喂 build-blueprint，无需 litematic）

用法:
  python img2blueprint.py <图片> --width 160 [--name foo] [--dither floyd|none]

输出:
  D:/mcserver/schematics/<name>.json     蓝图，可直接 build-blueprint 落地
  D:/work/minecraft/_img2bp/<name>_preview.png   方块配色预览
"""
import os
import sys
import json
import argparse
from collections import Counter

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

ENGINE = r'D:/mcserver'
OUTDIR = r'D:/work/minecraft/_img2bp'

# ---------- 调色板（1.21.x 原版方块的平均色，sRGB） ----------
PALETTE = {
    # 混凝土：鲜艳饱和，像素画主力
    'white_concrete':        (207, 213, 214),
    'light_gray_concrete':   (125, 125, 115),
    'gray_concrete':         ( 54,  57,  61),
    'black_concrete':        (  8,  10,  15),
    'brown_concrete':        ( 96,  59,  31),
    'red_concrete':          (142,  33,  33),
    'orange_concrete':       (224,  97,   0),
    'yellow_concrete':       (240, 175,  21),
    'lime_concrete':         ( 94, 168,  24),
    'green_concrete':        ( 73,  91,  36),
    'cyan_concrete':         ( 21, 119, 136),
    'light_blue_concrete':   ( 36, 137, 199),
    'blue_concrete':         ( 44,  46, 143),
    'purple_concrete':       (100,  32, 156),
    'magenta_concrete':      (169,  48, 159),
    'pink_concrete':         (213, 101, 142),
    # 羊毛：柔和，适合过渡
    'white_wool':            (233, 236, 236),
    'light_gray_wool':       (142, 142, 134),
    'gray_wool':             ( 62,  68,  71),
    'black_wool':            ( 20,  21,  25),
    'brown_wool':            (114,  71,  40),
    'red_wool':              (161,  39,  34),
    'orange_wool':           (240, 118,  19),
    'yellow_wool':           (248, 198,  39),
    'lime_wool':             (112, 185,  25),
    'green_wool':            ( 84, 109,  27),
    'cyan_wool':             ( 21, 137, 145),
    'light_blue_wool':       ( 58, 179, 218),
    'blue_wool':             ( 53,  57, 157),
    'purple_wool':           (121,  42, 172),
    'magenta_wool':          (189,  68, 179),
    'pink_wool':             (237, 141, 172),
    # 陶瓦：土色，照片里的低饱和区域靠它
    'white_terracotta':      (209, 177, 161),
    'light_gray_terracotta': (135, 107,  98),
    'gray_terracotta':       ( 57,  42,  35),
    'black_terracotta':      ( 37,  22,  16),
    'brown_terracotta':      ( 77,  51,  35),
    'red_terracotta':        (142,  60,  46),
    'orange_terracotta':     (161,  83,  37),
    'yellow_terracotta':     (186, 133,  35),
    'lime_terracotta':       (103, 117,  53),
    'green_terracotta':      ( 76,  82,  42),
    'cyan_terracotta':       ( 87,  91,  91),
    'light_blue_terracotta': (112, 108, 138),
    'blue_terracotta':       ( 74,  60,  91),
    'purple_terracotta':     (118,  70,  86),
    'magenta_terracotta':    (149,  87, 108),
    'pink_terracotta':       (162,  77,  86),
    # 石质 / 自然 / 装饰
    'quartz_block':          (237, 234, 228),
    'smooth_quartz':         (232, 228, 222),
    'stone':                 (126, 126, 126),
    'cobblestone':           (122, 122, 122),
    'andesite':              (138, 138, 138),
    'diorite':               (201, 201, 201),
    'deepslate':             ( 80,  80,  80),
    'sandstone':             (216, 205, 155),
    'oak_planks':            (184, 148,  95),
    'spruce_planks':         (115,  84,  50),
    'birch_planks':          (215, 200, 155),
    'dark_oak_planks':       ( 66,  43,  20),
    'bricks':                (150,  96,  78),
    'netherrack':            (112,  53,  54),
    'obsidian':              ( 20,  18,  30),
    'coal_block':            ( 16,  16,  16),
    'purpur_block':          (168, 120, 168),
    'amethyst_block':        (133,  97, 196),
    'prismarine':            ( 99, 156, 151),
    'dark_prismarine':       ( 51,  91,  75),
    'sea_lantern':           (197, 200, 187),
    'glowstone':             (167, 147, 102),
    'gold_block':            (248, 211,  60),
    'iron_block':            (219, 219, 219),
    'waxed_copper_block':    (193, 111,  78),
    'snow_block':            (249, 254, 254),
    'bone_block':            (229, 225, 207),
    'mossy_cobblestone':     (110, 118,  94),
}

NAMES = list(PALETTE.keys())
PAL_RGB = np.array([PALETTE[n] for n in NAMES], dtype=np.float64)


def srgb_to_lab(rgb):
    """rgb: N×3 float 0-255 -> Lab"""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ M.T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), (903.3 * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], -1)


def lab_to_srgb(lab):
    """Lab -> rgb 0-255 float（srgb_to_lab 的逆变换）"""
    lab = np.asarray(lab, dtype=np.float64)
    fy = (lab[..., 0] + 16) / 116
    fx = fy + lab[..., 1] / 500
    fz = fy - lab[..., 2] / 200
    xyz = np.stack([fx, fy, fz], -1)
    xyz = np.where(xyz ** 3 > 0.008856, xyz ** 3, (116 * xyz - 16) / 903.3)
    xyz = xyz * np.array([0.95047, 1.0, 1.08883])
    Mi = np.array([[3.2404542, -1.5371385, -0.4985314],
                   [-0.9692660, 1.8760108, 0.0415560],
                   [0.0556434, -0.2040259, 1.0572252]])
    c = xyz @ Mi.T
    c = np.where(c > 0.0031308, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055, 12.92 * c)
    return np.clip(c * 255.0, 0, 255)


def saturate(rgb, factor):
    """在 Lab 域放大彩度 a/b。

    室内暗光照片的色相正确但彩度偏低（这只橘猫实测 a=14，而人眼觉得鲜橘），
    量化到方块时就会掉进灰扑扑的棕系。factor>1 把色相拉回它"应该"的鲜艳度。
    """
    if factor is None or abs(factor - 1.0) < 1e-3:
        return rgb
    lab = srgb_to_lab(rgb)
    lab[..., 1] *= factor
    lab[..., 2] *= factor
    return lab_to_srgb(lab)


def resample(path, width):
    """按目标宽度等比缩放，返回 (rgb, alpha, 原始尺寸)"""
    im = Image.open(path).convert('RGBA')
    W, H = im.size
    height = max(1, int(round(width * H / W)))
    rs = Image.BOX if width < W else Image.LANCZOS
    sm = im.resize((width, height), rs)
    arr = np.asarray(sm).astype(np.float64)
    return arr[:, :, :3], arr[:, :, 3] / 255.0, (W, H)


def grow_bg_mask(rgb, local_tol=12.0, start_tol=30.0):
    """自适应泛洪抠背景。

    实拍照片的背景常有大幅光照梯度（这张桌面从阴影到高光 Lab 距离跨 13~44），
    任何全局色距阈值都会两头不讨好：调低了留背景，调高了删肤色。
    这里改用「沿相邻格自适应蔓延」：从画面边缘出发，只要相邻格的色距小于
    local_tol 就继续蔓延。平滑渐变的桌面能被一路走通，而人物四周的黑色描边
    是一道陡坎，蔓延会在此停住 —— 描边内部天然成为前景。
    """
    from collections import deque
    h, w, _ = rgb.shape
    lab = srgb_to_lab(rgb.reshape(-1, 3)).reshape(h, w, 3)
    band = max(1, min(h, w) // 25)
    ring = np.concatenate([
        rgb[:band, :].reshape(-1, 3), rgb[-band:, :].reshape(-1, 3),
        rgb[:, :band].reshape(-1, 3), rgb[:, -band:].reshape(-1, 3)])
    bg = np.median(ring, 0)
    blab = srgb_to_lab(bg[None, :])[0]

    vis = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not vis[y, x] and np.sqrt(((lab[y, x] - blab) ** 2).sum()) < start_tol:
                vis[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not vis[y, x] and np.sqrt(((lab[y, x] - blab) ** 2).sum()) < start_tol:
                vis[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not vis[ny, nx]:
                if np.sqrt(((lab[ny, nx] - lab[y, x]) ** 2).sum()) < local_tol:
                    vis[ny, nx] = True
                    q.append((ny, nx))
    return ~vis, bg


def auto_bg_mask(rgb, tol, keep_ratio=0.02, hole_tol=15.0):
    """估计背景并返回前景 mask。

    判据分两段：① 外圈中值色附近 tol 内的像素是背景候选；
    ② 只有与画面边缘连通的候选区才算真背景 —— 人物肤色虽可能与背景色相近，
    但被前景包住、不与边缘相连，因此不会误伤。这比单纯色距阈值稳得多。
    """
    from scipy import ndimage
    h, w, _ = rgb.shape
    band = max(1, min(h, w) // 25)
    ring = np.concatenate([
        rgb[:band, :].reshape(-1, 3), rgb[-band:, :].reshape(-1, 3),
        rgb[:, :band].reshape(-1, 3), rgb[:, -band:].reshape(-1, 3)])
    bg = np.median(ring, 0)
    lab = srgb_to_lab(rgb.reshape(-1, 3))
    blab = srgb_to_lab(bg[None, :])[0]
    d = np.sqrt(((lab - blab) ** 2).sum(1)).reshape(h, w)

    cand = d < tol
    lbl, n = ndimage.label(cand)
    if n == 0:
        return np.ones((h, w), bool), bg
    edge = np.unique(np.concatenate([lbl[0, :], lbl[-1, :], lbl[:, 0], lbl[:, -1]]))
    edge = edge[edge > 0]
    if len(edge) == 0:
        return np.ones((h, w), bool), bg
    fg = ~np.isin(lbl, edge)

    fg = ndimage.binary_opening(fg, np.ones((3, 3)))
    fg = ndimage.binary_closing(fg, np.ones((5, 5)))
    lbl2, n2 = ndimage.label(fg)
    if n2 > 1:
        sizes = ndimage.sum(fg, lbl2, range(1, n2 + 1))
        keep = np.zeros_like(fg)
        for li in np.argsort(sizes)[::-1][:4]:
            if sizes[li] > fg.size * keep_ratio:
                keep |= (lbl2 == li + 1)
        # 封闭空洞要区别对待：位于两人之间的桌面缝隙虽被人物轮廓包住、
        # 不与画面边缘连通，但颜色与背景一致，必须掏空；而真正的人物内部
        # 空洞（如手臂与身体围出的肤色区）颜色远离背景色，应填充保留。
        filled = ndimage.binary_fill_holes(keep)
        holes = filled & ~keep
        hl, hn = ndimage.label(holes)
        if hn:
            for hi in range(1, hn + 1):
                m = (hl == hi)
                pix = rgb[m]
                if pix.shape[0] == 0:
                    continue
                med = np.median(pix, 0)
                dh = np.sqrt(((srgb_to_lab(med[None, :])[0] - blab) ** 2).sum())
                if dh >= hole_tol:
                    keep |= m
        fg = keep
    return fg, bg


def quantize(lab, tree, pal_lab, dither):
    """Lab 空间最近邻 + 可选 Floyd-Steinberg 误差扩散，返回索引图"""
    H, W, _ = lab.shape
    if dither == 'none':
        _, idx = tree.query(lab.reshape(-1, 3))
        return idx.reshape(H, W).astype(np.int32)

    work = lab.copy()
    idx = np.zeros((H, W), dtype=np.int32)
    spread = ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16))
    for y in range(H):
        for x in range(W):
            px = work[y, x]
            _, k = tree.query(px)
            k = int(k)
            idx[y, x] = k
            err = px - pal_lab[k]
            for dx, dy, w in spread:
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H:
                    work[ny, nx] += err * w
    return idx


def render(idx, alpha, scale=4, bg=(26, 26, 30)):
    """把索引图渲染成预览 PNG"""
    H, W = idx.shape
    rgb = PAL_RGB[idx].astype(np.uint8)
    out = np.empty((H, W, 3), dtype=np.uint8)
    out[:] = bg
    mask = alpha >= 0.5
    out[mask] = rgb[mask]
    im = Image.fromarray(out).resize((W * scale, H * scale), Image.NEAREST)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('--width', type=int, default=128, help='目标宽度（格）')
    ap.add_argument('--name', default=None)
    ap.add_argument('--dither', default='floyd', choices=['floyd', 'none'])
    ap.add_argument('--bg', default='none', choices=['none', 'auto', 'grow'],
                    help='auto=全局色距阈值；grow=自适应泛洪（实拍照片首选）')
    ap.add_argument('--bg-tol', type=float, default=25.0, help='背景 Lab 距离阈值')
    ap.add_argument('--hole-tol', type=float, default=15.0,
                    help='封闭空洞归背景的 Lab 距离阈值（小于则掏空）')
    ap.add_argument('--max-colors', type=int, default=0, help='限制材质种类数，0=不限')
    args = ap.parse_args()

    name = args.name or os.path.splitext(os.path.basename(args.image))[0]
    name = ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in name)

    rgb, alpha, orig = resample(args.image, args.width)
    H, W, _ = rgb.shape
    print(f'原图 {orig[0]}×{orig[1]} → 目标 {W}×{H} 格')

    if args.bg == 'grow':
        fg, bg = grow_bg_mask(rgb, local_tol=args.bg_tol)
        alpha = np.where(fg, alpha, 0.0)
        print(f'背景 #{int(bg[0]):02X}{int(bg[1]):02X}{int(bg[2]):02X} '
              f'→ 保留前景 {fg.sum() * 100 / fg.size:.1f}%')
    elif args.bg == 'auto':
        fg, bg = auto_bg_mask(rgb, args.bg_tol, hole_tol=args.hole_tol)
        alpha = np.where(fg, alpha, 0.0)
        print(f'背景 #{int(bg[0]):02X}{int(bg[1]):02X}{int(bg[2]):02X} '
              f'→ 保留前景 {fg.sum() * 100 / fg.size:.1f}%')

    pal_lab = srgb_to_lab(PAL_RGB)
    tree = cKDTree(pal_lab)

    lab = srgb_to_lab(rgb)
    idx = quantize(lab, tree, pal_lab, args.dither)

    if args.max_colors and args.max_colors < len(NAMES):
        used = Counter(idx[j, i] for j in range(H) for i in range(W) if alpha[j, i] >= 0.5)
        top = sorted(k for k, _ in used.most_common(args.max_colors))
        sub_lab = pal_lab[top]
        sub_idx = quantize(lab, cKDTree(sub_lab), sub_lab, args.dither)
        idx = np.asarray(top, dtype=np.int32)[sub_idx]
        print(f'材质精简到 {len(top)} 种（原 {len(used)} 种）')

    blocks = []
    for j in range(H):
        for i in range(W):
            if alpha[j, i] < 0.5:
                continue
            blocks.append([i, H - 1 - j, 0, 'minecraft:' + NAMES[idx[j, i]]])

    os.makedirs(os.path.join(ENGINE, 'schematics'), exist_ok=True)
    os.makedirs(OUTDIR, exist_ok=True)
    bp_path = os.path.join(ENGINE, 'schematics', name + '.json')
    with open(bp_path, 'w', encoding='utf-8') as f:
        json.dump({'width': W, 'height': H, 'length': 1, 'blocks': blocks}, f)

    pv = render(idx, alpha)
    pv_path = os.path.join(OUTDIR, name + '_preview.png')
    pv.save(pv_path)

    cnt = Counter(NAMES[idx[j, i]] for j in range(H) for i in range(W) if alpha[j, i] >= 0.5)
    print(f'方块总数 {len(blocks)} | 用到 {len(cnt)} 种材质')
    total = max(len(blocks), 1)
    for n, c in cnt.most_common(10):
        print(f'   {n:24s} {c:6d}  ({c * 100 / total:.1f}%)')
    print(f'蓝图 → {bp_path}')
    print(f'预览 → {pv_path}')


if __name__ == '__main__':
    main()
