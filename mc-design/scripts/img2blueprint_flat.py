"""平涂像素图 → MC 蓝图（一条命令）

适用于拼豆图纸、十字绣图纸、像素画这类**只有少数几种平涂色**的源图。
和照片走同一套生成器，但要多两步预处理，否则成品会全是杂点：

  ① 归色（posterize）：源图里看着杂，其实只有 4~6 种真色，其余全是网格线、
     描边抗锯齿和源图自身的噪声/纹理混出的过渡色。先检出真色再硬归一遍。
  ② 关抖动（--dither none）：Floyd-Steinberg 是给照片做渐变过渡用的，
     用在平涂图上会把纯白身体撒满粉色/灰色麻点，是最大的坑。
  ③ 语义吸附：缩放后格子边界仍会混出一圈中间色（材质数虚高到 24 种），
     按 HSV 把方块归到黑/白/粉/黄等语义类，再按邻域多数收边。

用法：
  python img2blueprint_flat.py <图片> --width 74 --name hk [--bg-tol 10]
"""
import argparse
import json
import os
import subprocess
import sys
import numpy as np
from collections import Counter
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from img2blueprint import srgb_to_lab, PALETTE, ENGINE  # noqa: E402

BIN = np.array([5.0, 8.0, 8.0])          # Lab 分箱尺度
MERGE_DE = 16.0                          # 两色相距小于此值视为同色
MIN_PX = 120                             # 主色最少像素数
RESID_DE = 22.0                          # 残差大于此值算"没被覆盖"
RESID_AREA = 40                          # 残差连通块达到此面积才提升为新色


def _lab_bins(lab):
    key = np.floor(lab / BIN).astype(np.int32)
    cnt = Counter(map(tuple, key))
    return key, cnt


def _greedy(bins, min_px, merge_de):
    """按频次贪心选取，彼此 Lab 距离 > merge_de 才算新色"""
    picked = []
    for kk, n in bins.most_common():
        if n < min_px:
            break
        c = np.array(kk) * BIN + BIN / 2
        if all(((c - p) ** 2).sum() > merge_de ** 2 for p in picked):
            picked.append(c)
    return picked


def detect_palette(rgb, min_px=MIN_PX, merge_de=MERGE_DE, verbose=True):
    """检出源图的"真实平涂色"。

    步骤：
    ① 局部平坦度筛出"处于色块内部"的像素，先排掉大部分网格线与抗锯齿；
    ② 在这些像素上做 Lab 粗分箱计数 —— **不能按精确 RGB 元组计数**，色块内部
       有细微渐变，同一个白色会被拆成上千个只出现几次的值，一筛就全没了；
    ③ 按频次贪心选色（远距离才算新色）；
    ④ **残差回收**：主色量化后，若原图里存在成片的、离所有已选色都远的区域
       （典型是 Hello Kitty 的黄鼻子这种小面积高饱和纯色），说明它被误并进了
       邻近主色，把它整块提升为新色后重跑。这一步是必需的：单靠局部平坦度
       抓不到小色块——它们太窄，3×3 窗口必然碰到描边。
    """
    from scipy import ndimage

    mx = ndimage.maximum_filter(rgb, size=(3, 3, 1))
    mn = ndimage.minimum_filter(rgb, size=(3, 3, 1))
    flat = (mx - mn).max(2) < 20
    if flat.sum() < 500:
        flat = np.ones(rgb.shape[:2], bool)

    lab_flat = srgb_to_lab(rgb.reshape(-1, 3))[flat.reshape(-1)]
    key, bins = _lab_bins(lab_flat)
    centers = _greedy(bins, min_px, merge_de)
    # 用落在各箱内的真实像素均值回代，得到精确代表色
    flat_rgb = rgb.reshape(-1, 3)[flat.reshape(-1)]
    colors = np.array([
        flat_rgb[np.all(key == np.round((c - BIN / 2) / BIN).astype(np.int32), axis=1)].mean(0)
        for c in centers])

    # ④ 残差回收
    lab_all = srgb_to_lab(rgb.reshape(-1, 3))
    H, W = rgb.shape[:2]
    while True:
        ref_lab = srgb_to_lab(colors)
        d = np.sqrt(((lab_all[:, None, :] - ref_lab[None, :, :]) ** 2).sum(2)).min(1)
        bad = (d > RESID_DE).reshape(H, W)
        lbl, n = ndimage.label(bad)
        if n == 0:
            break
        sizes = ndimage.sum(bad, lbl, range(1, n + 1))
        big = [i + 1 for i in np.argsort(sizes)[::-1] if sizes[i] >= RESID_AREA]
        if not big:
            break
        add = []
        for li in big[:4]:
            m = (lbl == li).reshape(-1)
            add.append(rgb.reshape(-1, 3)[m].mean(0))
        add = np.array(add)
        # 与已有色去重
        add = np.array([c for c in add
                        if ((srgb_to_lab(c[None, :]) - ref_lab) ** 2).sum(1).min() > MERGE_DE ** 2])
        if not len(add):
            break
        colors = np.vstack([colors, add])

    if verbose:
        print('检出平涂色 %d 种：%s' % (len(colors), ', '.join(
            '#%02X%02X%02X' % tuple(c.astype(int)) for c in colors)))
    return colors


def posterize(path, out, verbose=True):
    """把全图量化到检出的平涂色上，抹掉网格线、抗锯齿与源图噪声"""
    im = Image.open(path).convert('RGB')
    rgb = np.asarray(im).astype(np.float64)
    refs = detect_palette(rgb, verbose=verbose)
    refs_lab = srgb_to_lab(refs)
    lab = srgb_to_lab(rgb.reshape(-1, 3))
    idx = ((lab[:, None, :] - refs_lab[None, :, :]) ** 2).sum(2).argmin(1)
    res = refs[idx].reshape(rgb.shape).astype(np.uint8)
    Image.fromarray(res).save(out)
    if verbose:
        cnt = Counter(idx.tolist())
        print('归色后各色占比：' + ', '.join(
            '#%02X%02X%02X %.1f%%' % (*refs[i].astype(int), cnt[i] * 100 / len(idx))
            for i, _ in cnt.most_common()))
    return out


import colorsys

_SEM = {}


def semantic(name):
    """按颜色把方块归类，不依赖具体方块名（量化器选哪个灰/黑都无所谓）"""
    if name in _SEM:
        return _SEM[name]
    r, g, b = [v / 255.0 for v in PALETTE[name]]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if v < 0.28:
        k = 'black'
    elif s < 0.18:
        k = 'white' if v > 0.75 else 'other'
    elif 0.72 < h < 0.95 or (h < 0.06 and s > 0.3):
        k = 'pink'
    elif 0.10 < h < 0.22:
        k = 'yellow'
    elif 0.35 < h < 0.55:
        k = 'green'
    elif 0.55 < h < 0.72:
        k = 'blue'
    else:
        k = 'other'
    _SEM[name] = k
    return k


def snap(path):
    """把杂色归到语义标准方块：材质数 24 → 4 左右。

    第一遍把所有能定性的格子收成该语义的标准方块（同为"白"的 snow_block /
    white_wool / white_concrete 合并，同为"黑"的 coal_block / deepslate 合并）；
    第二遍再把剩下的中间灰（抗锯齿带）按邻域多数收边。
    """
    d = json.load(open(path, encoding='utf-8'))
    V = {(x, y): b.replace('minecraft:', '') for x, y, z, b in d['blocks']}
    pri = {'black': 'coal_block', 'white': 'snow_block', 'pink': 'pink_concrete',
           'yellow': 'yellow_concrete', 'green': 'lime_concrete', 'blue': 'light_blue_concrete'}
    names = list(pri)
    V = {k: pri[semantic(v)] if semantic(v) != 'other' else v for k, v in V.items()}
    for _ in range(3):
        out = dict(V)
        for (i, j), c in V.items():
            if semantic(c) != 'other':
                continue
            raw = [V.get((i + di, j + dj)) for di in (-1, 0, 1) for dj in (-1, 0, 1)
                   if (di, dj) != (0, 0)]
            nb = [semantic(n) for n in raw if n]
            if not nb:
                continue
            out[(i, j)] = pri[max(names, key=lambda k: nb.count(k))]
        V = out
    d['blocks'] = [[x, y, 0, 'minecraft:' + b] for (x, y), b in V.items()]
    json.dump(d, open(path, 'w', encoding='utf-8'))
    print('吸附后材质 %d 种 %s' % (len(set(V.values())), Counter(V.values()).most_common(6)))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('--width', type=int, required=True)
    ap.add_argument('--name', required=True)
    ap.add_argument('--bg-tol', type=float, default=10.0)
    a = ap.parse_args()

    tmp = os.path.join(os.path.dirname(os.path.abspath(a.image)), '_flat_posterized.png')
    posterize(a.image, tmp)
    subprocess.run([sys.executable, os.path.join(HERE, 'img2blueprint.py'), tmp,
                    '--width', str(a.width), '--bg', 'auto', '--bg-tol', str(a.bg_tol),
                    '--dither', 'none', '--name', a.name], check=True)
    snap(os.path.join(ENGINE, 'schematics', a.name + '.json'))
    print('蓝图 → %s/schematics/%s.json' % (ENGINE, a.name))
