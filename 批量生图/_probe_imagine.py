# -*- coding: utf-8 -*-
"""探索Imagine页按钮结构 v2——分步取避免序列化None"""
import grok_cdp as g

g.connect(9333)

JS = r"""(()=>{
  const ce=document.querySelector('[contenteditable="true"]');
  if(!ce) return 'NO_INPUT';
  const cR=ce.getBoundingClientRect();
  const near=[...document.querySelectorAll('button')].filter(b=>{
    const r=b.getBoundingClientRect();
    return r.width>0 && r.width<70 && Math.abs(r.y-cR.y)<100;
  });
  return 'COUNT:'+near.length + ' | ' + near.map(b=>{
    const r=b.getBoundingClientRect();
    return [Math.round(r.x+r.width/2), Math.round(r.y+r.height/2),
            (b.innerText||'').trim().slice(0,12),
            b.getAttribute('aria-label')||b.getAttribute('title')||'-'].join(',');
  }).join(' ; ');
})()"""

print(g.ev(JS))
