#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""edge-tts 批量配音模板：逐镜生成MP3 + ffprobe实测时长 -> durations.json。
铁律：镜时长必须用实测配音时长（+0.4s动作尾），禁止先定固定时长再配台词。
依赖：pip install edge-tts；本机需有 ffprobe（ffmpeg 套件）。

用法：
  1. 把 LINES 换成你的剧本台词（编号/音色/台词/语速）
  2. python make_audio_template.py
  3. 输出 ./audio_out/镜NN.mp3 + durations.json（供排轨/字幕引用同一份时长）
如需代理：set HTTPS_PROXY=http://127.0.0.1:7890（edge-tts 自动识别）
"""
import subprocess, sys, os, json, time

AUD = './audio_out'
os.makedirs(AUD, exist_ok=True)

# 音色表：角色代称 -> edge-tts 音色名（全剧锁定复用，保证声音一致）
VI = {'xiao': 'zh-CN-YunxiNeural',    # 旁白/主角（少年感）
      'nan':  'zh-CN-YunyangNeural',  # 长辈/官员
      'jian': 'zh-CN-YunjianNeural'}  # 对手/狂傲角色

# 台词表：(编号, 音色, 台词, 语速)  语速默认+0%；慌张可用+10%，沉稳-5%
# ——替换成你自己的剧本台词——
lines = [
    ('01', 'xiao', '（旁白：开场背景，替换成你的台词）', '+0%'),
    ('02', 'nan',  '（角色对白示例，替换成你的台词）', '+0%'),
    ('03', 'xiao', '（同镜两段不同说话人时，用 03a/03b 编号）', '+0%'),
    ('03b', 'nan', '（03b 的台词）', '+10%'),
]

def tts(voice, text, rate, out):
    for _ in range(4):
        try:
            subprocess.run([sys.executable, '-m', 'edge_tts', '--voice', VI[voice], '--rate', rate,
                            '--text', text, '--write-media', out], capture_output=True, timeout=80)
            if os.path.exists(out) and os.path.getsize(out) > 5000:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False

def probe(f):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'csv=p=0', f], capture_output=True, text=True, encoding='utf-8')
    return round(float(r.stdout.strip()), 2)

result = {}
for num, v, text, rate in lines:
    out = f'{AUD}/镜{num}.mp3'
    if not tts(v, text, rate, out):
        print(f'镜{num} TTS FAILED')
        sys.exit(1)
    d = probe(out)
    result[num] = {'text': text, 'voice': v, 'dur': d, 'file': out}
    print(f'镜{num}: {d}s [{v}] {text[:20]}')

# 同镜两段（如 03a+03b）拼接成 镜03.mp3 的示例：
if any(k.endswith('a') for k in result):
    base = [k for k in result if k.endswith('a')][0][:-1]
    a, b = base + 'a', base + 'b'
    open(f'{AUD}/c{base}.txt', 'w').write(f"file '镜{a}.mp3'\nfile '镜{b}.mp3'\n")
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', f'c{base}.txt',
                    '-c', 'copy', f'镜{base}.mp3'.replace('mp4', 'mp3')],
                   capture_output=True, cwd=AUD, timeout=60)
    d = probe(f'{AUD}/镜{base}.mp3')
    result[base] = {'text': result[a]['text'] + '／' + result[b]['text'],
                    'voice': result[a]['voice'] + '+' + result[b]['voice'],
                    'dur': d, 'file': f'{AUD}/镜{base}.mp3'}
    print(f'镜{base}(合成): {d}s')

json.dump(result, open(f'{AUD}/durations.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
total = sum(x['dur'] for x in result.values() if not x['voice'].count('+'))
print('TOTAL speech:', round(total, 1), 's | 有效配音镜数:', len(result))
