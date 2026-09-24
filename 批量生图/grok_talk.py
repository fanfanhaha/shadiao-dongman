# -*- coding: utf-8 -*-
"""grok_talk.py — Grok Imagine 说话视频一键生成（CDP全链路，2026-09-09实测通过）

流程：帖子页 → 制作视频菜单 → Add Prompt → 720p/10s/音频开 → 填词 → 生成 → 等新post → 下载

用法：
  python grok_talk.py --post <帖子URL> --prompt "提示词" --out <保存路径> [--wait-min 6]
  python grok_talk.py --prompt "..." --out out.mp4        # 用当前已打开的帖子页

依赖 grok_cdp.py（9333端口CDP）。Edge 需带 --remote-debugging-port=9333
且用独立 user-data-dir 启动并保持 Grok 登录态。

关键经验（勿改）：
- OneTrust隐私弹窗会挡住菜单点击，必须先关
- 开菜单用五事件序列（pointerdown/mousedown/pointerup/mouseup/click）
- Add Prompt 用 CDP 真坐标点击；成功标志是 aria-label="生成视频" 按钮（无文字！）
- 提示词填在 contenteditable（tiptap），用 Input.insertText
- 生成后页面自动导航到新post，video[0] 即产物
- 下载必须走页面内同源fetch（直接HTTP会403）
"""
import argparse, base64, json, sys, time

import grok_cdp as g


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def dismiss_cookie_banner():
    """OneTrust隐私弹窗会挡点击，先关掉"""
    r = g.ev("""(()=>{
      const sdk=document.querySelector('#onetrust-consent-sdk');
      if(!sdk||!(sdk.offsetWidth||sdk.offsetHeight)) return 'none';
      const b=[...sdk.querySelectorAll('button')].find(b=>/确认|同意|Allow/.test(b.innerText||''));
      if(b){b.click();return 'closed';}
      return 'present-no-btn';
    })()""")
    if r == 'closed':
        time.sleep(1.5)
    return r


def open_video_panel():
    """点制作视频(五事件) → 点Add Prompt(真坐标) → 验证面板就绪。
    导航后React渲染需时间，带重试。"""
    fired = None
    for _ in range(15):  # 最多等30秒
        fired = g.ev("""(()=>{
          const fire=(el)=>['pointerdown','mousedown','pointerup','mouseup','click']
            .forEach(t=>el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window})));
          const bs=[...document.querySelectorAll('button,[role=button]')];
          const b=bs.find(x=>x.innerText.trim().startsWith('制作视频'));
          if(!b) return false; fire(b); return true;
        })()""")
        if fired:
            break
        time.sleep(2)
    if not fired:
        raise RuntimeError('找不到「制作视频」按钮（确认停在帖子详情页）')
    pos = None
    for attempt in range(8):
        time.sleep(1.8)  # 等菜单渲染
        pos = g.ev("""(()=>{
          const rows=[...document.querySelectorAll('div,span,button')].filter(e=>{
            const own=[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent.trim()).join('');
            return own==='Add Prompt';
          });
          if(!rows.length) return 'null';
          const r=rows[0].getBoundingClientRect();
          if(!r.width) return 'hidden';
          return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)});
        })()""")
        if pos not in ('null', 'hidden', None):
            break
        # 菜单确定是关的（检测不到），安全重点（React hydration未稳时首点可能无效）
        g.ev("""(()=>{
          const fire=(el)=>['pointerdown','mousedown','pointerup','mouseup','click']
            .forEach(t=>el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window})));
          const bs=[...document.querySelectorAll('button,[role=button]')];
          const b=bs.find(x=>x.innerText.trim().startsWith('制作视频'));
          if(b) fire(b); return true;
        })()""")
    if pos in ('null', 'hidden', None):
        raise RuntimeError('Add Prompt 菜单没出现')
    p = json.loads(pos)
    g.click(p['x'], p['y'])
    time.sleep(2.5)
    ok = g.ev("""(()=>!![...document.querySelectorAll('button')]
      .find(b=>(b.getAttribute('aria-label')||'')==='生成视频'))()""")
    if not ok:
        raise RuntimeError('视频面板没出现（生成视频按钮缺失）')
    return True


def set_param(aria, want_text, item_re):
    """通用参数设置：点开按钮→选项里点目标项→验证回显"""
    cur = g.ev(f"""(()=>{{const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='{aria}');return b?(b.innerText||'').trim():'null'}})()""")
    if cur == want_text:
        log(f'{aria} 已是 {want_text}')
        return True
    pos = g.ev(f"""(()=>{{
      const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='{aria}');
      if(!b) return 'null';
      const r=b.getBoundingClientRect();
      return JSON.stringify({{x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}});
    }})()""")
    if pos == 'null':
        raise RuntimeError(f'找不到按钮 {aria}')
    p = json.loads(pos)
    g.click(p['x'], p['y']); time.sleep(1)
    item = g.ev(f"""(()=>{{
      const els=[...document.querySelectorAll('button,[role=menuitem],[role=menuitemradio],[role=option]')]
        .filter(e=>/{item_re}/.test((e.innerText||'').trim()) && (e.offsetWidth||e.offsetHeight));
      if(!els.length) return 'null';
      const r=els[0].getBoundingClientRect();
      return JSON.stringify({{x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}});
    }})()""")
    if item == 'null':
        raise RuntimeError(f'{aria} 选项里没找到 /{item_re}/')
    q = json.loads(item)
    g.click(q['x'], q['y']); time.sleep(1)
    cur = g.ev(f"""(()=>{{const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='{aria}');return b?(b.innerText||'').trim():'null'}})()""")
    if cur != want_text:
        raise RuntimeError(f'{aria} 设置后回显={cur}，期望{want_text}')
    log(f'{aria} -> {want_text}')
    return True


def ensure_audio_on():
    pressed = g.ev("""(()=>{const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='视频音频');return b?b.getAttribute('aria-pressed'):'null'})()""")
    if pressed == 'true':
        log('视频音频 已开')
        return True
    if pressed == 'false':
        pos = g.ev("""(()=>{const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='视频音频');if(!b)return 'null';const r=b.getBoundingClientRect();return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)})})()""")
        p = json.loads(pos); g.click(p['x'], p['y']); time.sleep(0.8)
        now = g.ev("""(()=>{const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='视频音频');return b?b.getAttribute('aria-pressed'):'null'})()""")
        if now == 'true':
            log('视频音频 已开（本次点亮）')
            return True
        raise RuntimeError('点完后音频仍是关')
    raise RuntimeError(f'视频音频按钮状态异常: {pressed}')


def fill_prompt(text):
    ce = g.ev("""(()=>{const c=document.querySelector('[contenteditable=true]');if(!c)return 'null';const r=c.getBoundingClientRect();return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)})})()""")
    if ce == 'null':
        raise RuntimeError('找不到提示词输入框')
    p = json.loads(ce)
    g.click(p['x'], p['y']); time.sleep(0.3)
    # 全选清空
    g.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'modifiers': 2, 'key': 'a', 'code': 'KeyA', 'windowsVirtualKeyCode': 65})
    g.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'modifiers': 2, 'key': 'a', 'code': 'KeyA', 'windowsVirtualKeyCode': 65})
    g.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Delete', 'code': 'Delete', 'windowsVirtualKeyCode': 46})
    g.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Delete', 'code': 'Delete', 'windowsVirtualKeyCode': 46})
    time.sleep(0.2)
    g.call('Input.insertText', {'text': text})
    time.sleep(0.5)
    got = g.ev("""(()=>{const c=document.querySelector('[contenteditable=true]');return c?c.innerText.trim().length:0})()""")
    if not got or got < 10:
        raise RuntimeError(f'填词失败，输入框长度={got}')
    log(f'提示词已填({got}字)')
    return True


def click_generate():
    pos = g.ev("""(()=>{const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='生成视频');if(!b)return 'null';const r=b.getBoundingClientRect();return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)})})()""")
    if pos == 'null':
        raise RuntimeError('找不到生成视频按钮')
    p = json.loads(pos)
    g.click(p['x'], p['y'])
    log('已点生成视频')


def wait_new_post(old_url, max_min=6):
    """生成完成后页面自动导航到新post；返回新URL"""
    t0 = time.time()
    last_report = 0
    while time.time() - t0 < max_min * 60:
        time.sleep(6)
        url = g.ev('location.href')
        if url != old_url and '/imagine/post/' in url:
            log(f'已导航到新post: ...{url[-45:]}')
            return url
        el = int(time.time() - t0)
        if el - last_report >= 60:
            last_report = el
            log(f'等待生成... {el}s')
    raise TimeoutError(f'{max_min}分钟内没等到新post')


def wait_video_ready(max_sec=180):
    """新post页等video[0]加载出src且可播放"""
    t0 = time.time()
    while time.time() - t0 < max_sec:
        st = g.ev("""(()=>{const v=document.querySelector('video');
          return v?{src:v.src.slice(-40),rs:v.readyState,dur:v.duration}:{none:true}})()""")
        if st and not st.get('none') and st.get('src') and st.get('rs', 0) >= 2 and st.get('dur'):
            log(f"视频就绪 src=...{st['src']} dur={st['dur']:.2f}s")
            return True
        time.sleep(5)
    raise TimeoutError('新post视频超时未就绪')


def download_video(path):
    """页面内同源fetch→base64分块导出（直连HTTP会403）"""
    src = g.ev("""(()=>{const v=document.querySelector('video');return v&&v.src?v.src:'null'})()""")
    if src == 'null':
        raise RuntimeError('无视频src可下载')
    r = g.call('Runtime.evaluate', {
        'expression': f"""(async()=>{{
            try{{
                const r=await fetch("{src}",{{credentials:'include'}});
                if(!r.ok) return 'ERR:'+r.status;
                const b=await r.arrayBuffer();
                const u=new Uint8Array(b);
                let s=''; const CH=0x8000;
                for(let i=0;i<u.length;i+=CH) s+=String.fromCharCode.apply(null,u.subarray(i,i+CH));
                window.__dl=btoa(s);
                return 'LEN:'+b.byteLength;
            }}catch(e){{return 'ERR:'+e.message}}
        }})()""",
        'awaitPromise': True, 'returnByValue': True,
    })
    res = r.get('result', {}).get('value')
    if not str(res).startswith('LEN:'):
        raise RuntimeError(f'页面fetch失败: {res}')
    total = g.ev('window.__dl?window.__dl.length:0')
    if not total:
        raise RuntimeError('页面里没有__dl数据')
    CH = 4_000_000
    out = open(path, 'wb')
    got = 0
    n = 0
    while got < total:
        chunk = g.ev(f'window.__dl.substr({got},{CH})')
        out.write(base64.b64decode(chunk))
        got += len(chunk)
        n += 1
        log(f'  下载块{n}: {got}/{total}')
    out.close()
    import os
    log(f'已下载 {path} ({os.path.getsize(path)} bytes)')
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--post', help='帖子URL；不填用当前页')
    ap.add_argument('--prompt', required=True, help='台词提示词（含台词原文+声音+时点+画面约束）')
    ap.add_argument('--out', required=True, help='保存路径(.mp4)')
    ap.add_argument('--wait-min', type=int, default=6)
    ap.add_argument('--res', default='720p')
    ap.add_argument('--dur', default='10s')
    args = ap.parse_args()

    g.connect()
    log('CDP已连接')
    dismiss_cookie_banner()
    if args.post:
        g.nav(args.post)
        time.sleep(3)
        dismiss_cookie_banner()
    url0 = g.ev('location.href')
    log(f'当前页: ...{url0[-50:]}')

    # 完整面板标志=设置按钮存在（生成视频按钮是chat composer自带，不能当依据）
    panel_open = g.ev("""(()=>!![...document.querySelectorAll('button')]
      .find(b=>(b.getAttribute('aria-label')||'')==='视频分辨率'))()""")
    if panel_open:
        log('视频面板已开（含设置项），跳过开菜单')
    else:
        open_video_panel()
    set_param('视频分辨率', args.res, args.res.rstrip('p') + 'p')
    set_param('视频时长', args.dur, '^' + args.dur + '$')
    ensure_audio_on()
    fill_prompt(args.prompt)
    click_generate()
    wait_new_post(url0, args.wait_min)
    wait_video_ready()
    download_video(args.out)
    log('全链路完成 ✅')


if __name__ == '__main__':
    main()
