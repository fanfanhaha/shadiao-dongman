# -*- coding: utf-8 -*-
"""grok_download.py — 从Grok页面下载视频到项目
页面内同源fetch视频URL→base64分块经CDP传回，避开403。
用法：python grok_download.py <video索引或src片段> <保存路径>
"""
import grok_cdp as g, time, json, sys, base64

def get_full_src(key):
    """key=video索引或src片段，返回完整src"""
    return g.ev(f"""(()=>{{
      const vs=[...document.querySelectorAll('video')];
      let v=null;
      if(/^\\d+$/.test('{key}')) v=vs[parseInt('{key}')];
      else v=vs.find(v=>v.src.includes('{key}'));
      if(!v||!v.src) return 'null';
      return v.src;
    }})()""")

def fetch_b64(url):
    """页面内fetch→base64分块返回。返回拼接后的bytes"""
    # 先拿总长度
    total = g.ev(f"""(async()=>{{
      try{{
        const r=await fetch('{url}',{{credentials:'include'}});
        const b=await r.arrayBuffer();
        window.__dlb64=btoa(String.fromCharCode(...new Uint8Array(b)));
        return 'LEN:'+b.byteLength;
      }}catch(e){{return 'ERR:'+e.message}}
    }})()""")
    # async函数返回Promise，ev需要awaitPromise
    return total

def fetch_b64_await(url):
    r = g.call('Runtime.evaluate', {
        'expression': f"""(async()=>{{
            try{{
                const r=await fetch("{url}",{{credentials:'include'}});
                if(!r.ok) return 'ERR:'+r.status;
                const b=await r.arrayBuffer();
                const u=new Uint8Array(b);
                let s='';
                const CH=0x8000;
                for(let i=0;i<u.length;i+=CH) s+=String.fromCharCode.apply(null,u.subarray(i,i+CH));
                window.__dl=btoa(s);
                return 'LEN:'+b.byteLength;
            }}catch(e){{return 'ERR:'+e.message}}
        }})()""",
        'awaitPromise': True, 'returnByValue': True
    })
    return r.get('result', {}).get('value')

def pull_chunks(path):
    """从window.__dl分块取base64写文件"""
    total_len = g.ev("window.__dl?window.__dl.length:0")
    if not total_len:
        raise RuntimeError('页面里没有__dl数据')
    CH = 4_000_000  # 每块base64字符数
    out = open(path, 'wb')
    got = 0
    i = 0
    while got < total_len:
        chunk = g.ev(f"window.__dl.substr({got},{CH})")
        out.write(base64.b64decode(chunk))
        got += len(chunk)
        i += 1
        print(f'  块{i}: 累计{got}/{total_len}', flush=True)
    out.close()

if __name__ == '__main__':
    key, path = sys.argv[1], sys.argv[2]
    g.connect(); time.sleep(0.5)
    src = get_full_src(key)
    print('SRC:', src)
    if src == 'null':
        sys.exit('找不到目标video')
    r = fetch_b64_await(src)
    print('FETCH:', r)
    if not str(r).startswith('LEN:'):
        sys.exit('fetch失败')
    pull_chunks(path)
    import os
    print('DONE:', path, os.path.getsize(path), 'bytes')
