# -*- coding: utf-8 -*-
# 新会话路线：imagine首页 -> setFileInputFiles上传首帧 -> 设参数 -> 填词 -> 生成
import grok_cdp as g, time, json, sys

sys.path.insert(0, '.')
from grok_talk import set_param, ensure_audio_on, fill_prompt, click_generate, wait_new_post, wait_video_ready, download_video, log, dismiss_cookie_banner

IMG = r'.\assets\V9-E01-S01_首帧_骗子拍门.png'
OUT = r'.\assets\videos\candidates\V9-E01-S01_骗子说话_v2.mp4'
PROMPT = ('骗子盯着中年男人，急切开口说话，台词：陈叔，名额提前了，五百今晚交。'
          '年轻男性嗓音，油滑带催促，普通话。第1秒开始说，第5秒内说完，说完闭嘴保持讨好的笑，'
          '右手向前摊开要钱。旁边的父亲是老实巴交的中年农民，紧张皱眉，身体微微后缩，'
          '双手紧紧捂住上衣口袋，眼神犹豫不安，全程不抱臂。夜景室内，灯泡照明，两人位置不变。'
          '无旁白，无配乐，无字幕，无其他台词，口型与台词对应。')

g.connect(); time.sleep(0.5)
# 页面应已在 grok.com/imagine（上一命令已导航）；确认
url = g.ev('location.href')
assert '/imagine' in url, f'不在imagine页: {url}'
url0 = url

# 1. 找图片file input并直接塞文件（不弹原生对话框）
doc = g.call('DOM.getDocument', {'depth': -1})
r = g.call('DOM.querySelector', {'nodeId': doc['root']['nodeId'], 'selector': 'input[type=file][accept*="image"]'})
node_id = r.get('nodeId', 0)
log(f'图片input nodeId={node_id}')
if not node_id:
    sys.exit('没找到图片file input')
g.call('DOM.setFileInputFiles', {'files': [IMG], 'nodeId': node_id})
log('已设置文件，等图片挂载...')
time.sleep(5)

# 2. 验证composer里有图
st = g.ev("""(()=>{const box=document.querySelector('[data-testid=chat-input]')||document.body;
  return JSON.stringify({imgs:box.querySelectorAll('img').length})})()""")
log(f'composer图片: {st}')
imgs = json.loads(st)['imgs'] if st else 0
if not imgs:
    log('!! 图片没挂上，截图诊断')
    import base64
    r = g.call('Page.captureScreenshot', {'format':'jpeg','quality':55})
    open('_upload_diag.jpg','wb').write(base64.b64decode(r['data']))
    sys.exit(1)

# 3. 参数：720p / 6s / 音频开
set_param('视频分辨率', '720p', '720p')
set_param('视频时长', '6s', '^6s$')
ensure_audio_on()

# 4. 填词、生成
fill_prompt(PROMPT)
click_generate()
wait_new_post(url0, 8)
wait_video_ready()
download_video(OUT)
log('新会话路线全链路完成 ✅')
