# -*- coding: utf-8 -*-
"""grok_imagine_batch.py — Grok Imagine 批量生图（CDP，2026-09-10）

流程：imagine页 → tiptap输入框填提示词 → 回车提交 → 等图片生成 → 抓图下载(base64) → 下一张

用法：
  python grok_imagine_batch.py --task 任务.json --outdir 输出目录
任务JSON格式：[{"name":"文件名","prompt":"提示词"}, ...]

依赖 grok_cdp.py（9333端口）。图片下载走页面内同源fetch转base64（避403）。
"""
import argparse, base64, json, os, sys, time

import grok_cdp as g

sys.stdout.reconfigure(encoding='utf-8')

POLL = 3          # 轮询间隔秒
MAX_WAIT = 180    # 单图最长等待


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def fill_prompt(text):
    """tiptap contenteditable 填词（先聚焦再insertText）"""
    ce_js = """(()=>{
      const ce=document.querySelector('[contenteditable="true"]');
      if(!ce) return 'null';
      ce.focus();
      const r=ce.getBoundingClientRect();
      return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)});
    })()"""
    pos = g.ev(ce_js)
    if pos in ('null', None):
        raise RuntimeError('找不到输入框（确认在imagine页且已登录）')
    p = json.loads(pos)
    g.click(p['x'], p['y'])
    time.sleep(0.5)
    g.call('Input.insertText', {'text': text})
    time.sleep(0.8)
    # 验证写入
    got = g.ev("""(document.querySelector('[contenteditable="true"]')||{}).textContent||''""")
    return got.strip()


def submit():
    """回车提交"""
    g.call('Input.dispatchKeyEvent', {'type': 'keyDown',
                                     'key': 'Enter', 'code': 'Enter',
                                     'windowsVirtualKeyCode': 13, 'nativeVirtualKeyCode': 13})
    time.sleep(0.1)
    g.call('Input.dispatchKeyEvent', {'type': 'keyUp',
                                     'key': 'Enter', 'code': 'Enter',
                                     'windowsVirtualKeyCode': 13, 'nativeVirtualKeyCode': 13})


def newest_images():
    """抓当前页面所有大图URL（生成结果区）。含data:URI（新版UI内嵌base64图）"""
    return g.ev(r"""(()=>{
      const imgs=[...document.querySelectorAll('img')]
        .filter(i=>i.naturalWidth>300||i.width>300)
        .map(i=>i.src).filter(s=>s&&(s.startsWith('http')||s.startsWith('blob')||s.startsWith('data:image/')));
      return imgs.length?('OK:'+JSON.stringify(imgs.slice(-8))):'EMPTY';
    })()""")


def fetch_b64(url, out_path):
    """页面内fetch→base64→写文件。分块取回防CDP超载"""
    js = (
        '(async()=>{'
        '  try{'
        f'    const r=await fetch("{url}",{{credentials:"include"}});'
        '    if(!r.ok) return "ERR:"+r.status;'
        '    const b=await r.arrayBuffer();'
        '    const u=new Uint8Array(b);'
        '    let s="";'
        '    for(let i=0;i<u.length;i+=8192) s+=String.fromCharCode.apply(null,u.subarray(i,i+8192));'
        '    window.__b64=btoa(s);'
        '    return "LEN:"+u.length;'
        '  }catch(e){return "ERR:"+e.message}'
        '})()'
    )
    total = g.ev(js)
    if not total or not total.startswith('LEN:'):
        return f'download fail: {total}'
    n = int(total[4:])
    b64len = (n * 4 // 3) + 8
    step = 500000
    parts = []
    for off in range(0, b64len + step, step):
        seg = g.ev(f'window.__b64.slice({off},{off+step})')
        if seg:
            parts.append(seg)
    data = base64.b64decode(''.join(parts))
    with open(out_path, 'wb') as f:
        f.write(data)
    return f'ok {len(data)} bytes'


def save_datauri(uri, out_path):
    """data:URI图直接切base64写文件（URI挂window后分块取回）"""
    if ',' not in uri:
        return 'datauri fail: no comma'
    header, b64 = uri.split(',', 1)
    ext = 'png' if 'image/png' in header else 'jpg'
    out_path = os.path.splitext(out_path)[0] + '.' + ext
    g.ev(f'window.__du={json.dumps(uri)}')
    step = 400000
    parts = []
    off = len(header) + 1  # 跳过 "data:image/jpeg;base64,"
    while True:
        seg = g.ev(f'window.__du.slice({off},{off+step})')
        if not seg:
            break
        parts.append(seg)
        if len(seg) < step:
            break
        off += step
    try:
        data = base64.b64decode(''.join(parts))
        with open(out_path, 'wb') as f:
            f.write(data)
        return f'ok {len(data)} bytes'
    except Exception as e:
        return f'datauri decode fail: {e}'


def wait_and_grab(before_urls, name, outdir, want=1):
    """等新图出现（before_urls 之前的忽略），下载最新的want张。支持data:URI"""
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        time.sleep(POLL)
        r = newest_images()
        if not r or not r.startswith('OK:'):
            continue
        urls = json.loads(r[3:])
        fresh = [u for u in urls if u not in before_urls]
        if len(fresh) >= want:
            time.sleep(2)  # 等画质稳定（缩略图→原图替换）
            r2 = newest_images()
            if r2 and r2.startswith('OK:'):
                urls2 = json.loads(r2[3:])
                fresh = [u for u in urls2 if u not in before_urls]
            saved = []
            for i, u in enumerate(fresh[:want]):
                if u.startswith('data:image/'):
                    out = os.path.join(outdir, f'{name}#{i}' if want > 1 else f'{name}')
                    saved.append(save_datauri(u, out))
                    if not saved[-1].startswith('ok'):
                        return saved
                    continue
                if u.startswith('blob:'):
                    saved.append(f'skip blob:{u[:30]}')
                    continue
                out = os.path.join(outdir, f'{name}#{i}.png' if want > 1 else f'{name}.png')
                res = fetch_b64(u, out)
                saved.append(res)
                if not res.startswith('ok'):
                    return saved
            return saved
    return ['timeout']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--outdir', required=True)
    args = ap.parse_args()

    with open(args.task, encoding='utf-8') as f:
        tasks = json.load(f)
    os.makedirs(args.outdir, exist_ok=True)

    url = g.connect(9333)
    log(f'CDP已连: {url}')
    if '/imagine' not in url:
        g.nav('https://grok.com/imagine')
        time.sleep(3)
        log('已导航到imagine页')

    report = []
    for i, t in enumerate(tasks):
        name, prompt = t['name'], t['prompt']
        log(f'[{i+1}/{len(tasks)}] {name} 填词…')
        got = fill_prompt(prompt)
        if len(got) < 10:
            log(f'  填词失败(仅{len(got)}字)，重试一次')
            time.sleep(2)
            got = fill_prompt(prompt)
            if len(got) < 10:
                report.append({'name': name, 'result': 'fill_fail'})
                continue
        base = newest_images()
        base_urls = json.loads(base[3:]) if base and base.startswith('OK:') else []
        submit()
        log(f'  已提交，等生成（最长{MAX_WAIT}s）…')
        res = wait_and_grab(base_urls, name, args.outdir, want=t.get('want', 1))
        log(f'  结果: {res}')
        report.append({'name': name, 'result': res})
        time.sleep(4)  # 间隔防限流

    rp = os.path.join(args.outdir, '_report.json')
    with open(rp, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    ok = sum(1 for r in report if any(str(x).startswith('ok') for x in r['result']))
    log(f'完成 {ok}/{len(tasks)}，报告: {rp}')


if __name__ == '__main__':
    main()
