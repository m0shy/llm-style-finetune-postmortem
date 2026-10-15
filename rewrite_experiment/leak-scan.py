# -*- coding: utf-8 -*-
"""记忆泄漏扫描：GLM重写稿 vs 灵境原文（去标点归一化后找≥N字连续重合）。
用法: python 泄漏扫描.py [最小重合字数，默认12]
输出: 每章重合条数/最长重合/重合样例（可能=记忆泄漏 或 撞句）"""
import io, os, re, sys

BASE = r"<项目目录>/灵境重写实验"
MINN = int(sys.argv[1]) if len(sys.argv) > 1 else 12

def norm(t):
    return "".join(re.findall(r"[\u4e00-\u9fff]", t))

origs = {}
for f in sorted(os.listdir(os.path.join(BASE, "原文分章"))):
    if f.endswith(".md"):
        origs[f[:4]] = norm(io.open(os.path.join(BASE, "原文分章", f), encoding="utf-8").read())

rdir = os.path.join(BASE, "重写稿")
if not os.path.isdir(rdir):
    print("重写稿目录不存在"); sys.exit(1)

for f in sorted(os.listdir(rdir)):
    if not f.endswith(".md"):
        continue
    t = norm(io.open(os.path.join(rdir, f), encoding="utf-8").read())
    hits = {}  # 重合串 -> 原文章
    for i in range(0, len(t) - MINN + 1):
        ngram = t[i:i + MINN]
        for k, o in origs.items():
            if ngram in o:
                # 向两侧扩展到最长重合
                lo, hi = i, i + MINN
                while lo > 0 and t[lo - 1] in o and o.find(t[lo - 1:hi]) >= 0:
                    lo -= 1
                while hi < len(t) and t[lo:hi + 1] in o:
                    hi += 1
                s = t[lo:hi]
                hits[s] = k
                i = hi  # 跳过已命中区间（外层循环的 i 不受影响，仅示意）
                break
    # 合并子串
    uniq = [h for h in hits if not any(h != g and h in g for g in hits)]
    longest = max(uniq, key=len) if uniq else ""
    print(f"\n== {f}：重合{len(uniq)}处，最长{len(longest)}字（对应{hits.get(longest, '-')}）")
    for h in sorted(uniq, key=len, reverse=True)[:5]:
        print(f"   [{len(h)}字·{hits[h]}] {h[:60]}")
