# dhash匹配：每个视频首帧 vs 44张分镜图
import os, subprocess
from PIL import Image
import numpy as np

def dhash(path, size=16):
    img = Image.open(path).convert('L').resize((size+1, size))
    a = np.asarray(img, dtype=int)
    diff = a[:, 1:] > a[:, :-1]
    bits = diff.flatten()
    return bits

def hamming(a, b):
    return int(np.sum(a != b))

frames_dir = r'./flow_v_uuid/frames'
img_dir = r'./output'

# 分镜图dhash（跳过B版）
import re
imgs = {}
for f in sorted(os.listdir(img_dir)):
    if re.match(r'^\d{2}_', f) and not f.endswith('B.png'):
        imgs[f] = dhash(os.path.join(img_dir, f))

print('分镜图数:', len(imgs))
results = {}
for f in sorted(os.listdir(frames_dir)):
    if not f.endswith('.jpg'): continue
    uuid = f[:-4]
    fh = dhash(os.path.join(frames_dir, f))
    best = sorted(imgs.items(), key=lambda kv: hamming(fh, kv[1]))[:3]
    results[uuid] = [(k, hamming(fh, v)) for k, v in best]
    top = results[uuid][0]
    print(f'{uuid[:8]} -> 最像: {top[0]} (diff={top[1]})  候选2: {results[uuid][1][0]}({results[uuid][1][1]})')
