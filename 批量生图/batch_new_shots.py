# -*- coding: utf-8 -*-
# 批量生成E01新镜（纯文生视频，首页视频模式）：N1交钱闪回/N2围门要债/N3老王病床
import json, time, urllib.request, sys, subprocess

import grok_cdp as g
import websocket

OUTDIR = r'.\assets\videos\candidates'

SHOTS = [
    ('N1_交钱闪回',
     '夜晚昏暗室内，穿花衬衫、头顶架墨镜的年轻男人满脸堆笑，从中年农民父亲手里接过一叠旧钞，'
     '随手塞进自己棕色手提包。父亲穿深蓝工装白内衬，不舍地缓缓松手，垂下眼睛。'
     '九十年代中国农村风格，二维动漫，夜景灯泡照明。无旁白，无台词，无字幕，只有轻微环境音。'),
    ('N2_围门要债',
     '白天，九十年代中国农村土墙院门口，五六个穿着朴素的愤怒街坊围住一个低头作揖赔罪的老人。'
     '老人六十多岁，花白寸头，黝黑皱纹脸，穿灰色旧中山装，佝偻着背。'
     '人群指指点点，气氛压抑。二维动漫风格，白天自然光。无台词，无字幕，只有嘈杂人群环境音。'),
    ('N3_老王病床',
     '昏暗的九十年代乡镇医院病房，一位六十多岁花白寸头的老人躺在铁架病床上，闭眼憔悴，'
     '手背扎着输液针管，针管连着床头的玻璃输液瓶。床头柜上放着一个旧搪瓷缸。'
     '一位系围裙的中年妇女坐在床边低头抹泪。二维动漫风格，昏黄灯光。无台词，无字幕，安静环境音。'),
]

from grok_talk import set_param, ensure_audio_on, fill_prompt, log, download_video


def new_tab():
    ver = json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/version'))
    bws = websocket.create_connection(ver['webSocketDebuggerUrl'], timeout=30, suppress_origin=True)
    bws.send(json.dumps({'id': 1, 'method': 'Target.createTarget', 'params': {'url': 'https://grok.com/imagine'}}))
    tid = None
    for _ in range(10):
        m = json.loads(bws.recv())
        if m.get('id') == 1:
            tid = m['result']['targetId']; break
    bws.close()
    assert tid
    time.sleep(7)
    for _ in range(10):
        for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json')):
            if t.get('type') == 'page' and t['id'] == tid:
                g.WS = websocket.create_connection(t['webSocketDebuggerUrl'], timeout=120,
                                                   suppress_origin=True, max_size=None)
                return
        time.sleep(1)
    raise RuntimeError('新tab没找到')


for name, prompt in SHOTS:
    out = f'{OUTDIR}\\V9-E01-{name}.mp4'
    log(f'=== {name} ===')
    new_tab()
    time.sleep(3)
    g.ev("""(()=>{const sdk=document.querySelector('#onetrust-consent-sdk');
      if(sdk&&sdk.offsetWidth){const b=[...sdk.querySelectorAll('button')].find(b=>/确认|同意/.test(b.innerText||''));if(b)b.click();}return 1})()""")
    time.sleep(1.5)
    url0 = g.ev('location.href')
    # 首页视频模式面板
    set_param('视频分辨率', '720p', '720p')
    set_param('视频时长', '6s', '^6s$')
    ensure_audio_on()
    fill_prompt(prompt)
    pos = g.ev("""(()=>{const b=[...document.querySelectorAll('button')].find(b=>{
      const al=b.getAttribute('aria-label')||'';return al==='生成视频'||al==='提交';});
      if(!b)return 'null';const r=b.getBoundingClientRect();return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)})})()""")
    if pos == 'null':
        log(f'{name}: 首页无生成视频按钮，dump诊断')
        diag = g.ev("""(()=>JSON.stringify([...document.querySelectorAll('button')].map(b=>b.getAttribute('aria-label')||'').filter(a=>a)))()""")
        log(diag)
        sys.exit(1)
    p = json.loads(pos)
    g.click(p['x'], p['y'])
    log('已点生成')
    # 等新post（post id变化）
    t0 = time.time()
    new_url = None
    while time.time() - t0 < 8 * 60:
        time.sleep(6)
        url = g.ev('location.href')
        if url != url0 and '/imagine/post/' in url:
            new_url = url; break
    assert new_url, f'{name} 8分钟没等到新post'
    log(f'新post: ...{new_url[-40:]}')
    t0 = time.time()
    while time.time() - t0 < 240:
        st = g.ev("""(()=>{const v=document.querySelector('video');
      return v?{src:v.src.slice(-30),rs:v.readyState,dur:v.duration}:{none:true}})()""")
        if st and not st.get('none') and st.get('rs', 0) >= 4 and st.get('dur'):
            break
        time.sleep(5)
    else:
        sys.exit(f'{name} 视频超时')
    download_video(out)
    dur = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out],
                         capture_output=True, text=True).stdout.strip()
    log(f'{name} 完成 dur={dur}')
log('全部新镜完成 ✅')
