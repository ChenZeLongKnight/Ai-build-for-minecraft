# -*- coding: utf-8 -*-
"""
photo2blueprint.py — 照片 → MC 蓝图，一键流水线

  照片 --[主体提取 U2-Net]--> 抠图 --[紧裁]--> 像素化 --[Lab归色]--> 蓝图 JSON

主体提取做成可插拔模块：默认 u2net（显著性分割，任意照片通用）。
以后要换开放词汇检测（Grounded-SAM / YOLO-World），只需替换 salient_mask()。

用法:
  python photo2blueprint.py 照片.jpg --width 120 --name cat
  python photo2blueprint.py 照片.jpg --list              # 只列候选主体 + 出联络图，不生成蓝图
  python photo2blueprint.py 照片.jpg --pick 2 --width 120 # 图里有多个东西时选第 2 大的
  python photo2blueprint.py 照片.jpg --mode color         # 不跑模型，走旧的色距抠背景
  python photo2blueprint.py 照片.jpg --saturate 1.3       # 暗光照片增彩，让颜色落到更艳的方块
"""
import os
import sys
import json
import argparse
from collections import Counter

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from img2blueprint import (NAMES, PAL_RGB, srgb_to_lab, resample, quantize,
                           render, auto_bg_mask, grow_bg_mask, saturate,
                           ENGINE, OUTDIR)

MODEL_DIR = os.environ.get('SUBJECT_MODEL_DIR', r'C:/Users/ASUS/.workbuddy/models')
# 文件名 → 期望体积(MB)：顺序即质量优先级，同档取第一个完好可用的
MODEL_CANDIDATES = [
    ('u2net.onnx', 168.0),
    ('isnet-general-use.onnx', 170.0),
    ('silueta.onnx', 42.0),
    ('u2netp.onnx', 4.4),
]


_BAD_MODELS = set()


def _load_session(model_path):
    """真正把权重读进 onnxruntime；失败（半截/损坏）返回 None。"""
    if model_path in _BAD_MODELS:
        return None
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.intra_op_num_threads = 0
    try:
        return ort.InferenceSession(
            model_path, sess_options=so, providers=['CPUExecutionProvider'])
    except Exception as e:
        _BAD_MODELS.add(model_path)
        print(f'  [跳过] {os.path.basename(model_path)} 无法加载: {type(e).__name__}',
              file=sys.stderr)
        return None


def resolve_model(explicit=None):
    """按质量优先取第一个「体积正常 且 能真正加载」的权重。

    两道守门：体积过滤半截下载，加载自检过滤下载完整但已损坏的文件。
    """
    if explicit:
        return explicit
    env = os.environ.get('SUBJECT_MODEL')
    if env:
        return env
    for fn, mb in MODEL_CANDIDATES:
        p = os.path.join(MODEL_DIR, fn)
        if not os.path.exists(p) or os.path.getsize(p) < mb * 1048576 * 0.9:
            continue
        global _SESSION
        _SESSION = _load_session(p)
        if _SESSION is not None:
            return p
    for fn, _ in MODEL_CANDIDATES:
        p = os.path.join(MODEL_DIR, fn)
        if os.path.exists(p) and os.path.getsize(p) < 20 * 1048576:
            # 体积小但可能可用（如 u2netp），兜底再试一次
            if _load_session(p) is not None:
                return p
    return os.path.join(MODEL_DIR, MODEL_CANDIDATES[0][0])

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)

_SESSION = None


def get_session(model_path):
    global _SESSION
    if _SESSION is None:
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f'找不到分割模型 {model_path}\n'
                f'下载: curl -L -o "{model_path}" '
                f'https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx')
        _SESSION = _load_session(model_path)
        if _SESSION is None:
            raise RuntimeError(f'模型 {model_path} 无法加载，请重新下载完整文件')
    return _SESSION


def salient_mask(rgb, model_path, size=320):
    """U2-Net 显著性分割，返回与原图同尺寸的 0~1 浮点 mask。"""
    sess = get_session(model_path)
    in_name = sess.get_inputs()[0].name
    im = Image.fromarray(rgb).resize((size, size), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32)
    a = a / max(float(a.max()), 1e-6)
    a = (a - MEAN) / STD
    a = a.transpose(2, 0, 1)[None, ...].astype(np.float32)
    out = sess.run(None, {in_name: a})[0]
    pred = np.squeeze(out[:, 0, :, :])
    lo, hi = float(pred.min()), float(pred.max())
    pred = (pred - lo) / max(hi - lo, 1e-6)
    m = Image.fromarray((pred * 255).astype(np.uint8), 'L').resize(
        (rgb.shape[1], rgb.shape[0]), Image.LANCZOS)
    return np.asarray(m).astype(np.float32) / 255.0


def find_components(mask, thresh=0.5, min_ratio=0.004):
    """把 mask 拆成连通块，按面积从大到小返回候选列表。"""
    lab, n = ndimage.label(mask >= thresh)
    if n == 0:
        return [], lab
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    H, W = mask.shape
    out = []
    for i in range(n):
        r = sizes[i] / mask.size
        if r < min_ratio:
            continue
        ys, xs = np.where(lab == i + 1)
        out.append({
            'label': i + 1,
            'area_ratio': round(float(r), 4),
            'bbox': [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
            'cx': round(float(xs.mean() / W), 3),
            'cy': round(float(ys.mean() / H), 3),
        })
    out.sort(key=lambda d: -d['area_ratio'])
    return out, lab


def contact_sheet(rgb, cands, path):
    """把候选主体画上框和编号，供人选号。"""
    im = Image.fromarray(rgb).copy()
    if max(im.size) > 1200:
        im.thumbnail((1200, 1200), Image.LANCZOS)
    sx = im.size[0] / rgb.shape[1]
    sy = im.size[1] / rgb.shape[0]
    d = ImageDraw.Draw(im)
    for k, c in enumerate(cands, 1):
        x0, y0, x1, y1 = c['bbox']
        d.rectangle([x0 * sx, y0 * sy, x1 * sx, y1 * sy],
                    outline=(255, 90, 60), width=3)
        tx, ty = x0 * sx + 4, max(0, y0 * sy - 22)
        d.rectangle([tx - 2, ty - 2, tx + 24, ty + 20], fill=(255, 90, 60))
        d.text((tx + 4, ty + 3), str(k), fill=(255, 255, 255))
    im.save(path)
    return path


def make_cutout(rgb, mask, lab, keep_labels, pad=0.06):
    """按选定连通块抠出 RGBA 紧裁图。"""
    sel = np.isin(lab, keep_labels) if keep_labels else (mask >= 0.5)
    a = np.where(sel, np.clip(mask, 0.0, 1.0), 0.0)
    ys, xs = np.where(a > 0.02)
    if len(xs) == 0:
        return None
    H, W = a.shape
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    pw = int(round((x1 - x0 + 1) * pad))
    ph = int(round((y1 - y0 + 1) * pad))
    x0, x1 = max(0, x0 - pw), min(W - 1, x1 + pw)
    y0, y1 = max(0, y0 - ph), min(H - 1, y1 + ph)
    rgb_c = rgb[y0:y1 + 1, x0:x1 + 1]
    al = (a[y0:y1 + 1, x0:x1 + 1] * 255).astype(np.uint8)
    return np.dstack([rgb_c, al])


def clean_alpha(alpha, min_px=4, fill_holes=True):
    """格子空间的 mask 清理：去掉碎渣、补内部小孔。"""
    m = alpha >= 0.5
    if not m.any():
        return alpha
    lab, n = ndimage.label(m)
    thr = max(min_px, m.size * 0.0008)
    keep = np.zeros_like(m)
    for i in range(1, n + 1):
        if (lab == i).sum() >= thr:
            keep |= (lab == i)
    keep = ndimage.binary_closing(keep, np.ones((3, 3)))
    if fill_holes:
        keep = ndimage.binary_fill_holes(keep)
    return np.where(keep, 1.0, 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('--width', type=int, default=120, help='输出像素墙宽度（格）')
    ap.add_argument('--name', default=None)
    ap.add_argument('--mode', default='model', choices=['model', 'color', 'grow', 'none'],
                    help='model=U2-Net 显著性分割；color/grow=旧色距法；none=不抠')
    ap.add_argument('--model', default=None, help='分割权重路径，默认自动挑选')
    ap.add_argument('--thresh', type=float, default=0.5, help='mask 二值化阈值')
    ap.add_argument('--min-area', type=float, default=0.004, help='候选块最小占比')
    ap.add_argument('--pick', default='1',
                    help='选第几大的主体；1=最大；all=全部合并；也可逗号分隔如 1,3')
    ap.add_argument('--pad', type=float, default=0.06, help='紧裁外扩比例')
    ap.add_argument('--bg-tol', type=float, default=25.0)
    ap.add_argument('--dither', default='none', choices=['floyd', 'none'])
    ap.add_argument('--max-colors', type=int, default=0)
    ap.add_argument('--saturate', type=float, default=1.0,
                    help='彩度增强倍数（暗光照片可试 1.3~1.6，让颜色映射到更艳的方块）')
    ap.add_argument('--no-fill-holes', action='store_true')
    ap.add_argument('--list', action='store_true', help='只列候选主体，不生成蓝图')
    args = ap.parse_args()

    name = args.name or os.path.splitext(os.path.basename(args.image))[0]
    name = ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in name)
    os.makedirs(OUTDIR, exist_ok=True)

    img = Image.open(args.image).convert('RGB')
    rgb = np.asarray(img)
    print(f'输入 {args.image}  {rgb.shape[1]}×{rgb.shape[0]}')

    if args.mode == 'model':
        args.model = resolve_model(args.model)
        print(f'主体提取：显著性分割，权重 {os.path.basename(args.model)} …')
        mask = salient_mask(rgb, args.model)
        cands, lab = find_components(mask, args.thresh, args.min_area)
        if not cands:
            print('未检出主体，退回色距法。')
            fg, bg = auto_bg_mask(rgb, args.bg_tol)
            mask = fg.astype(np.float32)
            lab, _ = ndimage.label(mask >= 0.5)
            cands = [{'label': 1, 'area_ratio': 1.0,
                      'bbox': [0, 0, rgb.shape[1] - 1, rgb.shape[0] - 1],
                      'cx': 0.5, 'cy': 0.5}]
    else:
        if args.mode == 'grow':
            fg, bg = grow_bg_mask(rgb, local_tol=args.bg_tol)
        elif args.mode == 'color':
            fg, bg = auto_bg_mask(rgb, args.bg_tol)
        else:
            fg = np.ones(rgb.shape[:2], bool)
        mask = fg.astype(np.float32)
        lab, _ = ndimage.label(mask >= 0.5)
        cands = [{'label': 1, 'area_ratio': 1.0,
                  'bbox': [0, 0, rgb.shape[1] - 1, rgb.shape[0] - 1],
                  'cx': 0.5, 'cy': 0.5}]

    print(f'检出 {len(cands)} 个候选主体：')
    for k, c in enumerate(cands, 1):
        print(f'  [{k}] 占比 {c["area_ratio"] * 100:5.1f}%  '
              f'bbox {c["bbox"]}  中心 ({c["cx"]}, {c["cy"]})')

    sheet = contact_sheet(rgb, cands, os.path.join(OUTDIR, name + '_candidates.png'))
    print(f'候选联络图 → {sheet}')

    if args.list:
        print('（--list 模式，未生成蓝图）')
        return

    if args.pick.strip().lower() == 'all':
        keep = [c['label'] for c in cands]
    else:
        keep = []
        for t in args.pick.split(','):
            t = t.strip()
            if t.isdigit() and 1 <= int(t) <= len(cands):
                keep.append(cands[int(t) - 1]['label'])
        if not keep:
            print(f'--pick {args.pick} 越界，回退到最大主体。')
            keep = [cands[0]['label']]

    cut = make_cutout(rgb, mask, lab, keep, args.pad)
    if cut is None:
        print('抠图失败：选定区域为空。')
        return
    cut_path = os.path.join(OUTDIR, name + '_cut.png')
    Image.fromarray(cut, 'RGBA').save(cut_path)
    print(f'抠图 {cut.shape[1]}×{cut.shape[0]} → {cut_path}')

    rgb_s, alpha, orig = resample(cut_path, args.width)
    H, W, _ = rgb_s.shape
    alpha = clean_alpha(alpha, fill_holes=not args.no_fill_holes)
    fg_pct = alpha.sum() * 100 / alpha.size
    print(f'像素化 {W}×{H} 格，前景占 {fg_pct:.1f}%')

    pal_lab = srgb_to_lab(PAL_RGB)
    lab_img = srgb_to_lab(saturate(rgb_s, args.saturate))
    idx = quantize(lab_img, cKDTree(pal_lab), pal_lab, args.dither)

    if args.max_colors and args.max_colors < len(NAMES):
        used = Counter(idx[j, i] for j in range(H) for i in range(W) if alpha[j, i] >= 0.5)
        top = sorted(k for k, _ in used.most_common(args.max_colors))
        sub = pal_lab[top]
        idx = np.asarray(top, dtype=np.int32)[quantize(lab_img, cKDTree(sub), sub, args.dither)]

    blocks = [[i, H - 1 - j, 0, 'minecraft:' + NAMES[idx[j, i]]]
              for j in range(H) for i in range(W) if alpha[j, i] >= 0.5]

    os.makedirs(os.path.join(ENGINE, 'schematics'), exist_ok=True)
    bp = os.path.join(ENGINE, 'schematics', name + '.json')
    with open(bp, 'w', encoding='utf-8') as f:
        json.dump({'width': W, 'height': H, 'length': 1, 'blocks': blocks}, f)
    pv = os.path.join(OUTDIR, name + '_preview.png')
    render(idx, alpha).save(pv)

    cnt = Counter(NAMES[idx[j, i]] for j in range(H) for i in range(W) if alpha[j, i] >= 0.5)
    print(f'方块总数 {len(blocks)} | 材质 {len(cnt)} 种')
    for n, c in cnt.most_common(8):
        print(f'   {n:24s} {c:6d}  ({c * 100 / max(len(blocks), 1):.1f}%)')
    print(f'蓝图 → {bp}')
    print(f'预览 → {pv}')


if __name__ == '__main__':
    main()
