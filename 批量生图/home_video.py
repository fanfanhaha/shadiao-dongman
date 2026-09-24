# -*- coding: utf-8 -*-
# 首页视频模式路线v2：正确file input -> 等图挂载 -> 核参数 -> 填词 -> 生成 -> 严格验证 -> 下载
import json, time, urllib.request, sys

import grok_cdp as g
import websocket

OUT = r'.\assets\videos\candidates\V9-E01-S01_骗子说话_v2.mp4'
IMG = r'.\assets\V9-E01-S01_首帧_骗子拍门.png'
OLD_CONV = '2e1306da'
OLD_VID = '96d9d1bf3aff'
PROMPT = ('骗子盯着中年男人，急切开口说话，台词：陈叔，名额提前了，五百今晚交。'
          '年轻男性嗓音，油滑带催促，普通话。第1秒开始说，第5秒内说完，说完闭嘴保持讨好的笑，'
          '右手向前摊开要钱。旁边的父亲是老实巴交的中年农民，紧张皱眉，身体微微后缩，'
          '双手紧紧捂住上衣口袋，眼神犹豫不安，全程不抱臂。夜景室内，灯泡照明，两人位置不变。'
          '无旁白，无配乐，无字幕，无其他台词，口型与台词对应。')

tabs = [t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json'))
        if t.get('type') == 'page' and t.get('url', '').rstrip('/').endswith('grok.com/imagine')]
assert tabs, '没找到imagine首页tab'
g.WS = websocket.create_connection(tabs[0]['webSocketDebuggerUrl'], timeout=120, suppress_origin=True, max_size=None)
print('已连首页tab', flush=True)
time.sleep(1)

from grok_talk import set_param, ensure_audio_on, fill_prompt, log, download_video

url0 = g.ev('location.href')

# 1. 塞form内的 input[name=files]（上次实测能触发上传的那个）
doc = g.call('DOM.getDocument', {'depth': -1})
r = g.call('DOM.querySelector', {'nodeId': doc['root']['nodeId'], 'selector': 'form input[type=file][name=files]'})
node_id = r.get('nodeId', 0)
if not node_id:
    r = g.call('DOM.querySelector', {'nodeId': doc['root']['nodeId'], 'selector': 'input[name=files]'})
    node_id = r.get('nodeId', 0)
assert node_id, 'form file input没找到'
g.call('DOM.setFileInputFiles', {'files': [IMG], 'nodeId': node_id})
log('已塞入form input[name=files]')

# 2. 等"正在检测对象"出现再消失（最多90s），然后验证图挂上
t0 = time.time()
saw_detect = False
mounted = False
while time.time() - t0 < 90:
    st = g.ev("""(()=>({
      detecting: !![...document.querySelectorAll('div,span')].find(e=>e.childElementCount===0&&/正在检测/.test(e.innerText||'')),
      bigImg: (()=>{const im=[...document.querySelectorAll('img')].filter(i=>i.naturalWidth>500);return im.length})(),
      ph: (()=>{const p=document.querySelector('[contenteditable=true] p[data-placeholder]');return p?p.getAttribute('data-placeholder').slice(0,20):null})()
    }))()""")
    if st['detecting']:
        saw_detect = True
    if saw_detect and not st['detecting'] and st['bigImg']:
        mounted = True
        log(f"图挂载完成 ph={st['ph']} bigImg={st['bigImg']}")
        break
    time.sleep(3)
if not mounted:
    log(f'90秒图未挂载 saw_detect={saw_detect}，继续尝试（可能不需要检测阶段）')

# 3. 参数
set_param('视频分辨率', '720p', '720p')
set_param('视频时长', '6s', '^6s$')
ensure_audio_on()

# 4. 填词
fill_prompt(PROMPT)

# 5. 找提交按钮：aria-label=生成视频 或 表单内唯一激活按钮
pos = g.ev("""(()=>{const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='生成视频');
  if(!b)return 'null';const r=b.getBoundingClientRect();return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)})})()""")
if pos == 'null':
    log('aria生成视频按钮没有，dump表单按钮诊断')
    diag = g.ev("""(()=>{const ce=document.querySelector('[contenteditable=true]');
      const f=ce.closest('form');
      return JSON.stringify([...f.querySelectorAll('button')].map(b=>({al:b.getAttribute('aria-label'),dis:b.disabled})))})()""")
    log(f'表单按钮: {diag}')
    sys.exit('生成按钮没找到')
p = json.loads(pos)
g.click(p['x'], p['y'])
log('已点生成视频')

# 6. 严格等新会话
t0 = time.time()
new_url = None
while time.time() - t0 < 8 * 60:
    time.sleep(6)
    url = g.ev('location.href')
    if url != url0 and '/imagine/post/' in url and OLD_CONV not in url:
        new_url = url
        break
assert new_url, '8分钟没等到新会话post'
log(f'新会话: ...{new_url[-50:]}')

# 7. 新视频（排除旧src）
t0 = time.time()
while time.time() - t0 < 180:
    st = g.ev("""(()=>{const v=document.querySelector('video');
      return v?{src:v.src.slice(-40),rs:v.readyState,dur:v.duration}:{none:true}})()""")
    if st and not st.get('none') and st.get('rs', 0) >= 2 and st.get('dur') and OLD_VID not in st.get('src', 'x'):
        log(f"新视频就绪 {st['src']} dur={st['dur']:.2f}s")
        break
    time.sleep(5)
else:
    sys.exit('视频超时或仍是旧视频')

# 8. 下载+终验
download_video(OUT)
import subprocess
dur = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                      '-of', 'csv=p=0', OUT], capture_output=True, text=True).stdout.strip()
log(f'ffprobe时长: {dur}s（期望≈6）')
if float(dur) > 7:
    sys.exit('!! 时长不对，仍是10s版')
log('首页视频模式路线完成 ✅')
