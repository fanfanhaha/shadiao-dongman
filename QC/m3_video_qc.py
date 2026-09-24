#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""视频 M3 逐帧质检：ffmpeg 拆1fps帧 -> MiniMax-M3 按批识别 -> 逐条报告(JSON+MD)。
支持断点续跑（state.json 记录已完成视频）。key 从环境变量 MINIMAX_API_KEY 读取。

用法：
  set MINIMAX_API_KEY=你的key
  python m3_video_qc.py --glob "D:/你的项目/clips/*.mp4" --tag 我的剧集 [--proxy http://127.0.0.1:7890]
  # 可多次传 --glob 合并多组视频
"""
import os, sys, json, glob, time, argparse, tempfile, subprocess, base64, urllib.request

sys.stdout.reconfigure(encoding='utf-8')

KEY = os.environ.get('MINIMAX_API_KEY', '')
URL = os.environ.get('MINIMAX_URL', 'https://api.minimaxi.com/anthropic/v1/messages')
if not KEY:
    raise SystemExit('请先设置环境变量 MINIMAX_API_KEY')

PROMPT = """这是同一条AI生成视频中按时间顺序抽取的连续{batch}帧（第{start}秒到第{end}秒，每秒一帧）。
逐帧按固定格式输出，每帧一行，不要空话：
第N秒｜时段/光线｜主要人物(数量+外貌服装锚点)｜手持道具｜人物动作｜有无人张嘴说话｜问题(无 / 换脸漂移 / 道具消失或变形 / 站位闪变 / 物理穿帮 / 伪影变形 / 构图跳变)
最后单独一行"总结："，用一句话给出本段最严重的问题类型（若全段稳定则写"稳定"）。"""

def call_m3(opener, frame_paths, start_sec):
    content = [{"type": "text", "text": PROMPT.format(batch=len(frame_paths), start=start_sec,
                                                        end=start_sec + len(frame_paths) - 1)}]
    for f in frame_paths:
        data = base64.b64encode(open(f, 'rb').read()).decode()
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}})
    body = json.dumps({"model": "MiniMax-M3", "max_tokens": 4096,
                       "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        'Content-Type': 'application/json', 'x-api-key': KEY, 'anthropic-version': '2023-06-01'})
    for attempt in range(5):
        try:
            r = opener.open(req, timeout=300)
            out = json.loads(r.read())
            return ''.join(b.get('text', '') for b in out.get('content', [])).strip()
        except Exception as e:
            print(f'  M3失败({attempt + 1}/5): {str(e)[:120]}', flush=True)
            time.sleep(15 * (attempt + 1))
    return '[M3调用失败-重试5次]'

def analyze_video(opener, vid, tag, work, idx, total):
    name = os.path.basename(vid)
    print(f'[{tag} {idx}/{total}] {name}', flush=True)
    dur = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                          '-of', 'csv=p=0', vid], capture_output=True, text=True).stdout.strip()
    fdir = os.path.join(work, 'frames', tag, name.replace('.mp4', ''))
    os.makedirs(fdir, exist_ok=True)
    frames = sorted(glob.glob(os.path.join(fdir, 'f_*.png')))
    if not frames:
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', vid, '-vf', 'fps=1,scale=576:-2',
                        os.path.join(fdir, 'f_%03d.png')], capture_output=True)
        frames = sorted(glob.glob(os.path.join(fdir, 'f_*.png')))
    if not frames:
        return {'file': vid, 'duration': dur, 'frames': 0, 'analysis': '[抽帧失败]', 'summary': '抽帧失败'}
    texts = []
    for bi in range(0, len(frames), 5):
        bf = frames[bi:bi + 5]
        txt = call_m3(opener, bf, bi + 1)
        texts.append(txt)
        print(f'    第{bi + 1}-{bi + len(bf)}秒 ✓', flush=True)
        time.sleep(1.5)
    full = '\n\n'.join(texts)
    sums = [l for l in full.splitlines() if l.startswith('总结')]
    return {'file': vid, 'duration': dur, 'frames': len(frames), 'analysis': full,
            'summary': ' / '.join(s.replace('总结：', '').strip() for s in sums)[:200]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glob', action='append', required=True, help='视频glob模式，可多次传入')
    ap.add_argument('--tag', default='videos', help='分组名（用于报告命名）')
    ap.add_argument('--out', default='./qc_out', help='报告输出目录')
    ap.add_argument('--proxy', help='可选代理')
    args = ap.parse_args()

    opener = (urllib.request.build_opener(urllib.request.ProxyHandler(
        {'https': args.proxy, 'http': args.proxy})) if args.proxy
        else urllib.request.build_opener())
    work = os.path.join(tempfile.gettempdir(), 'm3_video_qc')
    os.makedirs(work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    state_path = os.path.join(work, f'state_{args.tag}.json')
    st = json.loads(open(state_path, encoding='utf-8')) if os.path.exists(state_path) else {'done': {}}

    vids = sorted({os.path.normpath(f) for g in args.glob for f in glob.glob(g)})
    print(f'{args.tag}: {len(vids)} 条', flush=True)
    results = []
    for i, vid in enumerate(vids, 1):
        if vid in st['done']:
            results.append(st['done'][vid])
            print(f'[{args.tag} {i}/{len(vids)}] 跳过(已完成)', flush=True)
            continue
        r = analyze_video(opener, vid, args.tag, work, i, len(vids))
        st['done'][vid] = r
        json.dump(st, open(state_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        results.append(r)

    json.dump(results, open(os.path.join(args.out, f'{args.tag}_逐帧质检.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    with open(os.path.join(args.out, f'{args.tag}_逐帧质检.md'), 'w', encoding='utf-8') as f:
        f.write(f'# {args.tag} 全量视频 M3 逐帧质检报告\n\n')
        f.write(f'共 {len(results)} 条，逐秒抽帧，分析模型 MiniMax-M3。\n\n')
        f.write('## 汇总表\n\n| 视频 | 时长 | 帧数 | M3结论 |\n|---|---|---|---|\n')
        for r in results:
            f.write(f"| {os.path.basename(r['file'])} | {r['duration'][:5] if r['duration'] else '?'}s"
                    f" | {r['frames']} | {r['summary'][:80]} |\n")
        f.write('\n## 逐条明细\n\n')
        for r in results:
            f.write(f"### {os.path.basename(r['file'])}（{r['duration'][:6] if r['duration'] else '?'}s / {r['frames']}帧）\n\n")
            f.write(f"```\n{r['analysis']}\n```\n\n")
    print(f'报告完成 → {os.path.join(args.out, args.tag)}', flush=True)

if __name__ == '__main__':
    main()
