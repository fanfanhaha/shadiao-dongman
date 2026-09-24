#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M3批量质检分镜图：查肢体异常/画面内文字/画风/内容偏差。
调用 MiniMax-M3（anthropic 兼容端点），key 从环境变量 MINIMAX_API_KEY 读取。
输出 qc_report.json（逐张 verdict+detail），FAIL 的列出待重生成。

用法：
  set MINIMAX_API_KEY=你的key
  python m3_batch_qc.py --img-dir ./output --expect qc_expect.json
  python m3_batch_qc.py --img-dir ./output --expect qc_expect.json --proxy http://127.0.0.1:7890

qc_expect.json 格式：{"图片名(无后缀)": "该图的期望内容描述"}，没登记的图按默认画风查。
"""
import os, base64, json, glob, time, argparse, urllib.request

KEY = os.environ.get('MINIMAX_API_KEY', '')
URL = os.environ.get('MINIMAX_URL', 'https://api.minimaxi.com/anthropic/v1/messages')
if not KEY:
    raise SystemExit('请先设置环境变量 MINIMAX_API_KEY')

ap = argparse.ArgumentParser()
ap.add_argument('--img-dir', required=True, help='分镜图目录')
ap.add_argument('--expect', help='期望内容json（图片名->期望描述）')
ap.add_argument('--out', default='qc_report.json', help='报告输出路径')
ap.add_argument('--proxy', help='可选代理，如 http://127.0.0.1:7890')
ap.add_argument('--default-expect', default='2D厚涂国风仙侠动画分镜', help='未登记图片的默认期望')
args = ap.parse_args()

opener = (urllib.request.build_opener(urllib.request.ProxyHandler(
    {'https': args.proxy, 'http': args.proxy})) if args.proxy
    else urllib.request.build_opener())
EXPECT = json.load(open(args.expect, encoding='utf-8')) if args.expect else {}

def ask(img_b64, prompt):
    body = {
        'model': 'MiniMax-M3', 'max_tokens': 600,
        'messages': [{'role': 'user', 'content': [
            {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': img_b64}},
            {'type': 'text', 'text': prompt}]}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={
        'Content-Type': 'application/json', 'x-api-key': KEY, 'anthropic-version': '2023-06-01'})
    for _ in range(3):
        try:
            r = opener.open(req, timeout=120)
            out = json.loads(r.read())
            return ''.join(c.get('text', '') for c in out['content'])
        except Exception as e:
            time.sleep(3)
    return 'REQ_FAIL: %s' % e

report, fails = {}, []
imgs = sorted(glob.glob(os.path.join(args.img_dir, '*.png')))
print(f'共{len(imgs)}张，开始质检…')
for i, p in enumerate(imgs, 1):
    name = os.path.basename(p)
    b64 = base64.b64encode(open(p, 'rb').read()).decode()
    exp = EXPECT.get(name.replace('.png', ''), args.default_expect)
    prompt = (f"质检这张竖屏动画分镜图（期望内容：{exp}）。只查四项，逐项回答：\n"
              f"1.肢体：手指是否融合/多余/缺失，肢体数量是否正常\n"
              f"2.画面内文字：是否出现任何文字或类文字符号\n"
              f"3.画风：是否与期望画风一致（不是照片/3D写实/其他风格）\n"
              f"4.内容：与期望内容是否相符（人物/动作/场景主要点）\n"
              f"最后单行给结论：PASS 或 FAIL:原因")
    txt = ask(b64, prompt)
    ok = txt.strip().upper().startswith('PASS') or '\nPASS' in txt.upper()[-80:]
    report[name] = {'verdict': 'PASS' if ok else 'FAIL', 'detail': txt[-500:]}
    if not ok:
        fails.append(name)
    print(f'[{i}/{len(imgs)}] {name}: {"PASS" if ok else "FAIL"}')

json.dump(report, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'\n结果：{len(imgs) - len(fails)} PASS / {len(fails)} FAIL')
if fails:
    print('待重生成：', fails)
