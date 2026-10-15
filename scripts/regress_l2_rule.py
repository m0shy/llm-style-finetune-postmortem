# -*- coding: utf-8 -*-
"""层2 B方案回归三件套.

对比 旧词表(_engine_old_ref.py) vs 新规则(lingjing_engine.py, 元叙述词需整段>=2命中):
  ① 185/187/522 正文零丢失(逐段字数对比 + 找回段落)
  ② 层2 已知 24 章 逐段剪除内容比对, 差异章逐章列出
  ③ 243/248 零变化 + 全部已交付章的段文本与数据集 99 条逐字比对
"""
import contextlib
import importlib.util
import io
import json
import os
import sys

BASE = r"<项目目录>\Datasets"
sys.path.insert(0, os.path.join(BASE, "scripts"))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


old = load(os.path.join(BASE, "scripts", "_engine_old_ref.py"), "engine_old")
new = load(os.path.join(BASE, "scripts", "lingjing_engine.py"), "engine_new")
loc = new.build_loc()

CH_L2 = [149, 153, 180, 185, 187, 209, 243, 247, 248, 283, 285, 316, 348,
         482, 484, 522, 570, 590, 647, 651, 910, 928, 1016, 1017]
CH_3 = [185, 187, 522]
DELIVERED = [1, 2, 3, 4, 5, 6, 12, 13, 15, 22, 47, 58] + list(range(243, 255))


def instrument(mod, tag, removed):
    holder = {"ch": None}
    orig = mod.trim_tail_note

    def wrapped(paras):
        out, n = orig(paras)
        gone = paras[len(out):]
        if gone:
            removed.setdefault((tag, holder["ch"]), []).extend(
                p.strip().strip("　") for p in gone)
        return out, n
    mod.trim_tail_note = wrapped
    return holder


def run(mod, chapters, holder):
    segs = {}
    for ch in chapters:
        holder["ch"] = ch
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                segs[ch] = {s["segment_id"]: s for s in mod.split_chapter(ch, loc)}
            except Exception as e:
                segs[ch] = {"__error__": {"original_text": str(e)}}
    return segs


rem_old, rem_new = {}, {}
h_old = instrument(old, "old", rem_old)
h_new = instrument(new, "new", rem_new)

targets = sorted(set(CH_L2) | set(DELIVERED))
segs_old = run(old, targets, h_old)
segs_new = run(new, targets, h_new)

print("=" * 66)
print("① 185 / 187 / 522 正文零丢失（逐段字数对比）")
print("=" * 66)
for ch in CH_3:
    ids = sorted(set(segs_old[ch]) | set(segs_new[ch]))
    print(f"\n第{ch}章（新引擎段数 {len(segs_new[ch])} / 旧 {len(segs_old[ch])}）")
    for sid in ids:
        o = segs_old[ch].get(sid, {}).get("original_text", "<无>")
        n = segs_new[ch].get(sid, {}).get("original_text", "<无>")
        mark = "  ←→ 变化" if o != n else ""
        print(f"  {sid}: 旧 {len(o)} 字 → 新 {len(n)} 字{mark}")
    # 找回的段落
    got = [p for p in rem_old.get(("old", ch), []) if p not in rem_new.get(("new", ch), [])]
    for p in got:
        meta_hits = len(new.META_NOTE_PAT.findall(p))
        print(f"  ✂️→✅ 找回正文段(元叙述命中{meta_hits}): {p[:60]}")

print()
print("=" * 66)
print("② 层2 已知 24 章 逐段剪除内容比对")
print("=" * 66)
diff_ch, same_ch = [], []
for ch in CH_L2:
    ids = sorted(set(segs_old[ch]) | set(segs_new[ch]))
    changed = [sid for sid in ids if segs_old[ch].get(sid, {}).get("original_text")
               != segs_new[ch].get(sid, {}).get("original_text")]
    ro = rem_old.get(("old", ch), [])
    rn = rem_new.get(("new", ch), [])
    if changed or ro != rn:
        diff_ch.append(ch)
    else:
        same_ch.append(ch)
print(f"剪除内容与旧词表完全一致: {len(same_ch)} 章 -> {same_ch}")
print(f"存在差异: {len(diff_ch)} 章 -> {diff_ch}\n")
for ch in diff_ch:
    print(f"--- 第{ch}章 ---")
    ids = sorted(set(segs_old[ch]) | set(segs_new[ch]))
    for sid in ids:
        o = segs_old[ch].get(sid, {}).get("original_text", "<无>")
        n = segs_new[ch].get(sid, {}).get("original_text", "<无>")
        if o != n:
            print(f"  {sid}: 旧 {len(o)} 字 -> 新 {len(n)} 字（差 {len(o) - len(n)} 字）")
    got = [p for p in rem_old.get(("old", ch), []) if p not in rem_new.get(("new", ch), [])]
    lost = [p for p in rem_new.get(("new", ch), []) if p not in rem_old.get(("old", ch), [])]
    for p in got:
        print(f"  ✅ 新规则保留(旧误剪): {p[:64]}")
    for p in lost:
        print(f"  ⚠️ 新规则剪除(旧未剪): {p[:64]}")
    print()

print("=" * 66)
print("③ 243 / 248 零变化 + 已交付章与数据集 99 条比对")
print("=" * 66)
for ch in (243, 248):
    ids = sorted(set(segs_old[ch]) | set(segs_new[ch]))
    bad = [sid for sid in ids if segs_old[ch].get(sid, {}).get("original_text")
           != segs_new[ch].get(sid, {}).get("original_text")]
    print(f"第{ch}章: {'✅ 零变化' if not bad else '❌ 变化段 ' + str(bad)}")

L = [json.loads(l) for l in open(os.path.join(BASE, "dataset_lingjing.jsonl"), encoding="utf-8")]
mismatch = []
for r in L:
    sid = r["metadata"]["segment_id"]
    ch = int(sid[4:8])
    t = segs_new[ch].get(sid, {}).get("original_text")
    if t is None or t != r["output"]:
        mismatch.append(sid)
print(f"数据集 99 条 vs 新引擎段文本: {'✅ 全部逐字一致（零变化）' if not mismatch else '❌ 不一致: ' + str(mismatch)}")

json.dump({"same": same_ch, "diff": diff_ch},
          open(os.path.join(BASE, "tmp", "regress_l2.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
