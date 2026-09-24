# Grok CDP操控核心（flow_produce.py同款骨架）
import json, urllib.request, time, websocket, sys
sys.stdout.reconfigure(encoding='utf-8')
WS=None; RID=[0]
def connect(port=9333):
    global WS
    tabs=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json'))
    grok=[t for t in tabs if t['type']=='page' and 'grok.com' in t['url']]
    target=grok[0] if grok else [t for t in tabs if t['type']=='page'][0]
    WS=websocket.create_connection(target['webSocketDebuggerUrl'],timeout=120,suppress_origin=True,max_size=None)
    return target['url']
def call(method,params=None):
    RID[0]+=1; i=RID[0]
    WS.send(json.dumps({'id':i,'method':method,'params':params or {}}))
    while True:
        m=json.loads(WS.recv())
        if m.get('id')==i: return m.get('result',{})
def ev(expr):
    r=call('Runtime.evaluate',{'expression':expr,'returnByValue':True})
    return r.get('result',{}).get('value')
def nav(url):
    call('Page.navigate',{'url':url}); time.sleep(3)
def click(x,y):
    call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':x,'y':y-20}); time.sleep(0.15)
    call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':x,'y':y}); time.sleep(0.25)
    call('Input.dispatchMouseEvent',{'type':'mousePressed','x':x,'y':y,'button':'left','clickCount':1}); time.sleep(0.08)
    call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':x,'y':y,'button':'left','clickCount':1})
def click_el(selector_js):
    """直接DOM点击——绕过自绘菜单不响应模拟鼠标的问题"""
    return ev(f"(()=>{{const b={selector_js}; if(!b) return 'null'; b.click(); return 'ok'}})()")
if __name__=='__main__':
    u=connect(); print('已连接:',u)
    nav('https://grok.com/imagine')
    time.sleep(4)
    t=ev("document.body.innerText") or ''
    print('登录态:' , '已登录' if 'fan xue' in t or 'Imagine' in t else '未登录/需登录')
