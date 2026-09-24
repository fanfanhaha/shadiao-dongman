# -*- coding: utf-8 -*-
# browser级Target.createTarget开新tab（不受弹窗拦截）→ 帖子详情页 → Add Prompt → 6s生成
import json, time, urllib.request

import grok_cdp as g

POST = 'https://grok.com/imagine/post/7d09feaf-d40b-45ab-aeaf-1db0bfd0d7d3'
OUT = r'.\assets\videos\candidates\V9-E01-S01_骗子说话_v2.mp4'
PROMPT = ('骗子盯着中年男人，急切开口说话，台词：陈叔，名额提前了，五百今晚交。'
          '年轻男性嗓音，油滑带催促，普通话。第1秒开始说，第5秒内说完，说完闭嘴保持讨好的笑，'
          '右手向前摊开要钱。旁边的父亲是老实巴交的中年农民，紧张皱眉，身体微微后缩，'
          '双手紧紧捂住上衣口袋，眼神犹豫不安，全程不抱臂。夜景室内，灯泡照明，两人位置不变。'
          '无旁白，无配乐，无字幕，无其他台词，口型与台词对应。')

# 1. browser级ws开新tab
import websocket
ver = json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/version'))
bws = websocket.create_connection(ver['webSocketDebuggerUrl'], timeout=30, suppress_origin=True)
bws.send(json.dumps({'id': 1, 'method': 'Target.createTarget', 'params': {'url': POST}}))
tid = None
for _ in range(10):
    m = json.loads(bws.recv())
    if m.get('id') == 1:
        tid = m['result']['targetId']
        break
bws.close()
assert tid, 'createTarget失败'
print('新tab targetId:', tid, flush=True)

# 2. 等新tab加载，找到它的tab级ws连上
time.sleep(5)
tab_ws = None
for _ in range(10):
    for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json')):
        if t.get('type') == 'page' and t['id'] == tid:
            tab_ws = t['webSocketDebuggerUrl']
            break
    if tab_ws:
        break
    time.sleep(1)
assert tab_ws, '新tab的ws没找到'
g.WS = websocket.create_connection(tab_ws, timeout=120, suppress_origin=True, max_size=None)
print('已连新tab', flush=True)

# 3. 等加载 + 关cookie弹窗
time.sleep(4)
g.ev("""(()=>{const sdk=document.querySelector('#onetrust-consent-sdk');
  if(sdk&&sdk.offsetWidth){const b=[...sdk.querySelectorAll('button')].find(b=>/确认|同意/.test(b.innerText||''));if(b)b.click();}
  return 1})()""")
time.sleep(1.5)

# 4. 复用grok_talk全流程
from grok_talk import open_video_panel, set_param, ensure_audio_on, fill_prompt, click_generate, wait_new_post, wait_video_ready, download_video, log

url0 = g.ev('location.href')
log(f'新tab页: ...{url0[-40:]}')
open_video_panel()
set_param('视频分辨率', '720p', '720p')
set_param('视频时长', '6s', '^6s$')
ensure_audio_on()
fill_prompt(PROMPT)
click_generate()
wait_new_post(url0, 8)
wait_video_ready()
download_video(OUT)
log('全新tab路线完成 ✅')
