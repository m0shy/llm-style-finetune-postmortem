# -*- coding: utf-8 -*-
"""通用批次构建器: 把某个批次的客观大纲并入主数据集, 并跑双向核对.
用法: python build_batch.py --outlines meta/outlines_batch2.json --segs tmp/seg_12_12.json tmp/seg_13_13.json tmp/seg_22_22.json
"""
import json, os, sys, argparse, glob

BASE = r"<项目目录>\Datasets"
INSTRUCTION = ("请根据以下剧情大纲，撰写一段小说正文。要求：极具画面感与节奏感，多用短句，"
               "注重感官描写（视觉/听觉/触觉），禁止使用'首先/其次/总之'等公文连接词，"
               "通过具体的动作和微表情展现人物心理，严禁直接陈述情绪。")

# 差异化模板(方案3): 用于"规则/资料发现"类片段
INSTRUCTION_RULE = ("请根据以下核心规则/线索，描写角色在紧张处境中发现并理解它们的过程。要求："
                    "严禁直接罗列设定或像说明书一样陈述。必须通过角色的具体动作、感官体验"
                    "（如看到某物时的生理反应）、心理活动以及与环境的互动，将这些规则自然地"
                    "'展示'出来（Show, don't tell）。")

INSTRUCTION_MAP = {"special_rule_discovery": INSTRUCTION_RULE}


def load_segs(paths):
    m = {}
    for p in paths:
        for x in json.load(open(p, encoding="utf-8")):
            m[x["segment_id"]] = x
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outlines", required=True)
    ap.add_argument("--segs", nargs="+", required=True)
    ap.add_argument("--master", default=os.path.join(BASE, "dataset_lingjing.jsonl"))
    a = ap.parse_args()

    outlines = json.load(open(a.outlines, encoding="utf-8"))
    segs = load_segs(a.segs)

    master = [json.loads(l) for l in open(a.master, encoding="utf-8")] if os.path.exists(a.master) else []
    byid = {r["metadata"]["segment_id"]: r for r in master}

    added, rep = [], []
    for sid, o in outlines.items():
        if sid not in segs:
            print("!! 找不到段:", sid); continue
        s = segs[sid]
        miss = [c for c in o["checks"] if c not in s["original_text"]]
        rev = [(lab, all(k in o["input"] for k in keys)) for lab, keys in o["turnings"]]
        rec = {
            "instruction": INSTRUCTION_MAP.get(o.get("instruction_override"), INSTRUCTION),
            "input": o["input"],
            "output": s["original_text"],
            "metadata": {"segment_id": sid,
                         "source_position": f"第{s['chapter']}章 {s['chapter_title']}"},
        }
        if sid in byid:
            print("覆盖已有:", sid)
        byid[sid] = rec
        added.append(rec)
        rep.append({"segment_id": sid, "chars": len(o["input"]), "points": len(o["checks"]),
                    "missed": miss, "rev_gap": [lab for lab, ok in rev if not ok]})

    allr = list(byid.values())
    with open(a.master, "w", encoding="utf-8") as f:
        for r in allr:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(allr, open(os.path.join(BASE, "dataset_lingjing_creator.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\n新增 {len(added)} 条，主数据集累计 {len(allr)} 条")
    L = [x["chars"] for x in rep]
    if L:
        print(f"input 长度: {min(L)}-{max(L)}（均值 {sum(L)//len(L)}）")
    bad = 0
    for x in rep:
        flag = "OK" if not x["missed"] and not x["rev_gap"] else "!!"
        bad += (flag == "!!")
        print(f"  {flag} {x['segment_id']} {x['chars']}字 {x['points']}点" +
              (f"  正向缺:{x['missed']}" if x["missed"] else "") +
              (f"  反向缺:{x['rev_gap']}" if x["rev_gap"] else ""))
    print("异常条数:", bad)


if __name__ == "__main__":
    main()
