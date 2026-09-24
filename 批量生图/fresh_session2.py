# -*- coding: utf-8 -*-
# 续：等"正在检测对象"完成 -> 图挂上 -> 设6s -> 填词 -> 生成 -> 下载
import grok_cdp as g, time, json, sys

from grok_talk import set_param, ensure_audio_on, fill_prompt, click_generate, wait_new_post, wait_video_ready, download_video, log

OUT = r'.\assets\videos\candidates\V9-E01-S01_骗子说话_v2.mp4'
PROMPT = ('骗子盯着中年男人，急切开口说话，台词：陈叔，名额提前了，五百今晚交。'
          '年轻男性嗓音，油滑带催促，普通话。第1秒开始说，第5秒内说完，说完闭嘴保持讨好的笑，'
          '右手向前摊开要钱。旁边的父亲是老实巴交的中年农民，紧张皱眉，身体微微后缩，'
          '双手紧紧捂住上衣口袋，眼神犹豫不安，全程不抱臂。夜景室内，灯泡照明，两人位置不变。'
          '无旁白，无配乐，无字幕，无其他台词，口型与台词对应。')

g.connect(); time.sleep(0.5)
url0 = g.ev('location.href')

# 1. 等"正在检测对象"结束（最多60s）
for i in range(20):
    st = g.ev("""(()=>({
      detecting: !![...document.querySelectorAll('div,span')].find(e=>e.childElementCount===0&&/正在检测/.test(e.innerText||'')),
      anyImg: [...document.querySelectorAll('img')].filter(im=>im.naturalWidth>300).length
    }))()""")
    if i % 4 == 0:
        log(f'检测中状态: {st}')
    if not st['detecting']:
        log(f'检测完成 imgs={st["anyImg"]}')
        break
    time.sleep(3)
else:
    log('60秒还在检测，继续往下试')

# 2. 图挂载验证：查页面里有没有我们上传的图（大图>300px宽，排除图标）
st = g.ev("""(()=>({
  big: [...document.querySelectorAll('img')].filter(im=>im.naturalWidth>300).map(im=>({src:im.src.slice(-30),w:im.naturalWidth})),
  composerImgs: (()=>{const ce=document.querySelector('[contenteditable=true]');const box=ce?ce.closest('form')||ce.parentElement.parentElement:null;return box?box.querySelectorAll('img').length:-1})()
}))()""")
log(f'图状态: {json.dumps(st, ensure_ascii=False)}')

# 3. 参数
set_param('视频分辨率', '720p', '720p')
set_param('视频时长', '6s', '^6s$')
ensure_audio_on()

# 4. 生成
fill_prompt(PROMPT)
click_generate()
wait_new_post(url0, 8)
wait_video_ready()
download_video(OUT)
log('新会话路线完成 ✅')
