# -*- coding: utf-8 -*-
"""语料风格统计: 对指定章节区间输出语言指纹.
用法: python style_stats.py --range 1 30
"""
import sys, os, re, statistics, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lingjing_engine import get_chapter, build_loc

ONOMAT = re.compile(r'^[“"]?[嚯嗬咚哒哐当咔咔嚓咯吱呼哧噔咣嗵砰嗖呜啊哈嘿～]{1,7}[”"]?[。！.～]*$')


def run(lo, hi):
    loc = build_loc()
    plens, slens = [], []
    dial = pan = onom = npara = 0
    for c in range(lo, hi + 1):
        if c not in loc:
            continue
        _, paras = get_chapter(c, loc)
        for p in paras:
            t = p.replace("　", "").strip()
            if not t:
                continue
            npara += 1
            plens.append(len(t))
            if re.match(r'^[“"]', t):
                dial += 1
            if t.startswith("【"):
                pan += 1
            if ONOMAT.match(t):
                onom += 1
            slens += [len(s.strip()) for s in re.split(r'[。！？…\n]+', t) if s.strip()]
    print(f"=== 第{lo}-{hi}章 风格统计 ===")
    print(f"段落 {npara} / 句 {len(slens)}")
    print(f"段落均长 {statistics.mean(plens):.1f}  中位 {statistics.median(plens):.1f}  最长 {max(plens)}")
    print(f"句均长 {statistics.mean(slens):.1f}  中位 {statistics.median(slens):.1f}  std {statistics.pstdev(slens):.1f}")
    print(f"短句<=6 占比 {sum(1 for x in slens if x<=6)/len(slens)*100:.1f}%")
    print(f"长句>=40 占比 {sum(1 for x in slens if x>=40)/len(slens)*100:.1f}%")
    print(f"对话起手段落 {dial/npara*100:.1f}%")
    print(f"面板【段落 {pan/npara*100:.2f}% ({pan})")
    print(f"拟声/独词成段 {onom/npara*100:.2f}% ({onom})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--range", nargs=2, type=int, default=[1, 30])
    a = ap.parse_args()
    run(a.range[0], a.range[1])
