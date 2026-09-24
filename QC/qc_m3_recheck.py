#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M3返修复检：只查各返修图的"必须修正"项，不重复全项质检。
key 从环境变量 MINIMAX_API_KEY 读取。

用法：把 CHECKS 按你的返修清单填写（文件名 -> 该图必须通过的检查点），
  set MINIMAX_API_KEY=你的key
  python qc_m3_recheck.py --img-dir ./output [--proxy http://127.0.0.1:7890]
"""
import os, json, base64, time, argparse, urllib.request

KEY = os.environ.get('MINIMAX_API_KEY', '')
URL = os.environ.get('MINIMAX_URL', 'https://api.minimaxi.com/anthropic/v1/messages')
if not KEY:
    raise SystemExit('请先设置环境变量 MINIMAX_API_KEY')

# 示例：按返修清单填写，键为图片文件名
CHECKS = {
    '示例_手部返修.png': '手部五指是否清晰无粘连？画风是否与全片一致？',
    '示例_表情返修.png': '人物表情是否符合指定情绪？背景人物是否穿帮？',
}

ap = argparse.ArgumentParser()
ap.add_argument('--img-dir', required=True, help='返修图所在目录')
ap.add_argument('--proxy', help='可选代理')
args = ap.parse_args()

opener = (urllib.request.build_opener(urllib.request.ProxyHandler(
    {'https': args.proxy, 'http': args.proxy})) if args.proxy
    else urllib.request.build_opener())

def ask(img_b64, prompt):
    body = {'model': 'MiniMax-M3', 'max_tokens': 400, 'messages': [{'role': 'user', 'content': [
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
            err = e
            time.sleep(3)
    return 'REQ_FAIL: %s' % err

for name, q in CHECKS.items():
    p = os.path.join(args.img_dir, name)
    b64 = base64.b64encode(open(p, 'rb').read()).decode()
    txt = ask(b64, f"只查这一张图：{q}\n逐项短答，最后单行结论：PASS 或 FAIL:原因")
    print(f'{name} => {txt[-200:]}')
    print('-' * 60)
