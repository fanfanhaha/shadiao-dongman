# -*- coding: utf-8 -*-
"""文稿自检脚本：机器项自动检查（2026-09-09起，剧本commit前必跑）

用法：
    python -X utf8 制作工具/文稿自检.py <剧本md路径> [--protagonist 主角全名 ...] [--v3]

机器项（自动）：
    1. 主角全名在台词中是否出现（角色标注不算）
    2. 旁白占比
    3. 单集时长估算（按每句3.2秒+0.5秒间隔）
    4. 出场角色清单（供人肉核对白名单）
    5. 情绪K线+大放配压（v2）

v3增补（--v3 开关，仅后续新剧本用；不加则行为与旧版一致）：
    6. 每集【名场面】标注≥1、每集【金句】标注≥1
    7. "算了/忍了/大度"式台词检测（主角蔫坏授权违规）
    8. 剧目录下《00_伏笔登记表.md》存在性

人肉项（必须手动过清单并写入剧本尾部"自检记录"）：
    观众可懂性1-4、骗局事后反推、情绪爆点间隔、卡点强度
"""
import sys, re, argparse, json, os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script_md")
    ap.add_argument("--protagonist", action="append", default=[])
    ap.add_argument("--max-seconds", type=float, default=130.0)
    ap.add_argument("--v3", action="store_true",
                    help="启用v3增补检查（名场面/金句标注、蔫坏违规词、伏笔登记表），仅后续新剧本用")
    a = ap.parse_args()

    text = open(a.script_md, encoding="utf-8").read()
    issues, warns, oks = [], [], []

    # 提取所有 "### 台词" 区块（支持一文件多集）
    # 角色行通用匹配：1-6字角色名+全角冒号（排除表格|、标题#、黑屏说明行）
    ROLE_LINE = re.compile(r"^([^：#|，。！？\s]{1,6})：(.+)$")
    blocks = re.findall(r"### 台词\n(.*?)(?=### |\Z)", text, re.S)
    spoken_lines = []
    for b in blocks:
        for ln in b.splitlines():
            m = ROLE_LINE.match(ln.strip())
            if m:
                spoken_lines.append((m.group(1), m.group(2)))

    if not spoken_lines:
        issues.append("未找到台词区块（### 台词）或无有效台词行")

    # 1. 主角全名
    all_spoken = "".join(t for _, t in spoken_lines)
    for p in (a.protagonist or ["陈向东", "陆小满", "陈稳"]):
        hit = all_spoken.count(p)
        (oks if hit >= 1 else issues).append(f"主角全名[{p}]台词中出现{hit}次（要求≥1）")

    # 2. 旁白占比
    narr = sum(1 for r, _ in spoken_lines if r == "旁白")
    total = len(spoken_lines)
    if total:
        ratio = narr / total
        (oks if ratio <= 0.55 else warns).append(f"旁白占比 {narr}/{total}={ratio:.0%}（公式≤55%；闪回/独白结构可放宽但需在自检记录说明）")

    # 3. 时长估算（每集独立估算：按台词块切分）
    for i, b in enumerate(re.findall(r"### 台词\n(.*?)(?=### |\Z)", text, re.S), 1):
        n = len([l for l in b.splitlines() if ROLE_LINE.match(l.strip())])
        est = n * 3.7
        (oks if est <= a.max_seconds else warns).append(f"第{i}集估算时长≈{est:.0f}秒（{n}句×3.7s，上限{a.max_seconds:.0f}）")

    # 4. 角色清单
    roles = sorted({r for r, _ in spoken_lines})
    oks.append(f"出场角色：{'、'.join(roles)}")

    # 5. 情绪K线（v2：解析台词行尾〖±n〗标记）
    VAL = re.compile(r"〖([+-]?\d)〗\s*$")
    for i, b in enumerate(re.findall(r"### 台词\n(.*?)(?=### |\Z)", text, re.S), 1):
        vals, missing = [], 0
        for ln in b.splitlines():
            m = ROLE_LINE.match(ln.strip())
            if not m:
                continue
            vm = VAL.search(ln)
            if vm:
                vals.append(int(vm.group(1)))
            else:
                vals.append(0); missing += 1
        if not vals:
            continue
        # 文本K线：每格5字符宽
        kline = "".join(("▁▂▃▄▅" if v >= 0 else "▅▄▃▂▁")[min(abs(v), 4)] + ("↑" if v > 0 else "↓" if v < 0 else "·") for v in vals)
        press = sum(1 for v in vals if v <= -2); release = sum(1 for v in vals if v >= 2)
        # 大放前20秒内需有压：近似为每4句内（4句≈15-20秒）
        unpaired = []
        for j, v in enumerate(vals):
            if v >= 4 and not any(x <= -3 for x in vals[max(0, j-4):j]):
                unpaired.append(j+1)
        if missing:
            warns.append(f"第{i}集有{missing}句未标情绪值（按0计）")
        (warns if unpaired else oks).append(
            f"第{i}集情绪K线：{''.join(kline)} ｜ 压{press}句/放{release}句" +
            (f" ｜ ⚠️第{unpaired}句大放前无大压" if unpaired else " ｜ 大放配压✅"))
        # 连续同极性>4句警告
        run, prev = 0, 0
        for v in vals:
            same = (v <= -2 and prev <= -2) or (v >= 2 and prev >= 2)
            run = run + 1 if same else 1
            prev = v
        if run >= 5:
            warns.append(f"第{i}集结尾连续{run}句同极性，节奏可能疲")

    # ===== v3增补检查（--v3 开关）=====
    if a.v3:
        for i, b in enumerate(re.findall(r"### 台词\n(.*?)(?=### |\Z)", text, re.S), 1):
            scenes = len(re.findall(r"【名场面[：:】]", b))
            quotes = len(re.findall(r"【金句[：:】]", b))
            (oks if scenes >= 1 else issues).append(f"v3第{i}集【名场面】标注{scenes}处（要求≥1）")
            (oks if quotes >= 1 else issues).append(f"v3第{i}集【金句】标注{quotes}处（要求≥1）")
        soft = re.findall(r"^.*(算了[，。]|忍了吧|忍了[，。]|不跟[他她]们计较|大人有大量).*$", text, re.M)
        if soft:
            warns.append(f"v3疑似'忍让式收尾'台词{len(soft)}处（蔫坏授权：占理必反击），逐条人工确认：" + " / ".join(s.strip()[:30] for s in soft[:3]))
        else:
            oks.append("v3无'忍让式收尾'违规词")
        drama_dir = os.path.dirname(os.path.abspath(a.script_md))
        fb = None
        for d in (drama_dir, os.path.dirname(drama_dir)):
            cand = os.path.join(d, "00_伏笔登记表.md")
            if os.path.isfile(cand):
                fb = cand
                break
        (oks if fb else warns).append(
            f"v3伏笔登记表：{os.path.relpath(fb) if fb else '未找到（要求剧目录下00_伏笔登记表.md，新剧第1集交审前建立）'}")

    print("== 机器自检结果 ==")
    for x in issues: print("❌ FAIL:", x)
    for x in warns: print("⚠️ WARN:", x)
    for x in oks:   print("✅ OK  :", x)
    print("\n提醒：人肉项（可懂性/骗局反推/爆点间隔/卡点）必须手动过清单，并把本脚本输出+人肉结论写入剧本尾部'## 自检记录'后才能commit。")
    sys.exit(1 if issues else 0)

if __name__ == "__main__":
    main()
