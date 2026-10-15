# -*- coding: utf-8 -*-
"""全库作者话扫描(权威版): 直接调用引擎 split_chapter, 捕获其过滤/修剪日志与剪除明细.

不重复实现规则, 而是复用引擎本身的段级判定, 保证与实际抽取完全一致.
四层定义(引擎内实现, 2026-09-11 裁决一·B方案后):
  层1 整段排除   : 段文本命中 AUTHOR_NOTE_PAT >= 3 次 -> 该段不进数据集
  层2 尾部批注   : 段末命中 硬批注词(结构/生活经营/请假口语变体) 单次即剪;
                   创作元叙述类泛指词需【整段】命中 >=2 才剪, 单词命中不剪
  层4 段尾符号归一化 : 段尾整段只有 …/—/~/－ 等符号 -> 剔除(非作者话过滤, 是排版归一化)
用法:
  python scan_author_notes.py              # 全库
  python scan_author_notes.py 302 352      # 指定章区间(含层2触发明细)
"""
import contextlib
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))
import lingjing_engine as E  # noqa: E402

LOG_RE = re.compile(r"\[(过滤|修剪)\] 第(\d+)章 第(\d+)段 (.*)")
SEP_PAT = re.compile(r"[…⋯—\-－~～\s]{2,}")


def classify_removed(p):
    """返回 (层, 命中词列表) —— 对单个被剪除的自然段定层."""
    words_hard = E.TAIL_NOTE_HARD_PAT.findall(p)
    words_hard = [w if isinstance(w, str) else "".join(w) for w in words_hard]
    words_meta = E.META_NOTE_PAT.findall(p)
    if E.SEP_PAT.fullmatch(p):
        return "层4 段尾符号归一化(非作者话)", []
    if words_hard:
        return "层2 硬批注", words_hard
    if words_meta:
        return "层2 元叙述(段内>=%d命中)" % E.META_MIN_HITS, words_meta
    return "层2 其他", []


def scan(chapters=None):
    loc = E.build_loc()
    all_no = sorted(loc.keys()) if chapters is None else sorted(chapters)
    hits = []
    for no in all_no:
        removed = []

        holder = {"ch": None}
        orig = E.trim_tail_note

        def wrapped(paras):
            out, n = orig(paras)
            gone = paras[len(out):]
            if gone:
                removed.extend(p.strip().strip("　") for p in gone)
            return out, n
        E.trim_tail_note = wrapped
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                E.split_chapter(no, loc)
            logs = buf.getvalue()
        except Exception as e:
            hits.append({"chapter": no, "layers": ["读取异常"], "actions": [str(e)[:70]]})
            continue
        finally:
            E.trim_tail_note = orig

        actions, layers = [], set()
        for line in logs.splitlines():
            m = LOG_RE.search(line.strip())
            if not m:
                continue
            kind, ch, k, msg = m.groups()
            if kind == "过滤":
                layers.add("层1 整段排除")
                actions.append(f"第{k}段 整段排除({msg.replace('判定为作者话','').replace('-> 已排除','').strip()})")
            else:
                layers.add("层2/4 尾部修剪")
                actions.append(f"第{k}段 尾部修剪({msg.strip()})")
        detail = []
        for p in removed:
            layer, words = classify_removed(p)
            detail.append({"layer": layer, "chars": len(p), "words": words, "text": p[:50]})
            layers.add(layer.split("（")[0].split("(")[0])
        if actions or detail:
            hits.append({"chapter": no, "layers": sorted(layers),
                         "actions": actions, "removed": detail})
    return hits


if __name__ == "__main__":
    chs = [int(x) for x in sys.argv[1:3]] if len(sys.argv) >= 3 else None
    h = scan(chs)
    n1 = sum(1 for x in h if "层1 整段排除" in x["layers"])
    n2 = sum(1 for x in h if "层2 硬批注" in x["layers"])
    n2m = sum(1 for x in h if any(l.startswith("层2 元叙述") for l in x["layers"]))
    n4 = sum(1 for x in h if any(l.startswith("层4 段尾符号归一化") for l in x["layers"]))
    scope = f"第{chs[0]}-{chs[1]}章" if chs else "全库 1,020 章"
    print(f"=== 扫描({scope}): 命中 {len(h)} 章 | 层1 {n1} / 层2硬 {n2} / 层2元叙述 {n2m} / 层4归一化 {n4} ===")
    for x in h:
        head = f"第{x['chapter']}章 | {' + '.join(x['layers'])} | " + " ; ".join(x["actions"])
        print(head)
        for d in x.get("removed", []):
            w = "/".join(d["words"][:6])
            print(f"    ✂️ [{d['layer']}] {d['chars']}字 命中:{w} | {d['text']}")
    out = os.path.join(BASE, "meta", "作者话扫描清单.json") if chs is None else \
        os.path.join(BASE, "meta", f"作者话扫描_{chs[0]}_{chs[1]}.json")
    json.dump(h, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写出", os.path.relpath(out, BASE))
