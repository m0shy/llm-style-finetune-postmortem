# -*- coding: utf-8 -*-
"""v3 指令强化器：在 v2（指令多样化）基础上，补三条"硬约束"，直击实测硬伤。

实测硬伤 → 对应新增约束：
  ① 丢信息点（漏"三道山娘娘五指合拢"）      → 【逐条落实】必须覆盖大纲每个信息点，不得遗漏
  ② 编造情节（自造"噗通摔倒"）              → 【不得增删】不得新增大纲之外的转折
  ③ 解说腔（"干尸不重要，重要的是…"）        → 【禁解剖心理】不得出现人物自述式的心理分析
  ④ 只会改写不会扩写（零环境细节）          → 【细节自生】环境/感官细节须自行铺陈，不得仅复述大纲用词

输入: dataset_lingjing_final.jsonl
输出: dataset_lingjing_v3.jsonl

用法: python scripts/build_v3_instructions.py
"""
import json, os, io, sys, hashlib

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass
BASE = r'<项目目录>\Datasets'
SRC = os.path.join(BASE, 'dataset_lingjing_final.jsonl')
DST = os.path.join(BASE, 'dataset_lingjing_v3.jsonl')

STYLE = ("画面感强、节奏张弛有度，长短句交错；注重感官描写（视觉/听觉/触觉）；"
         "用具体的动作和微表情展现人物心理，不要直接陈述情绪；"
         "禁用“首先/其次/总之”等公文连接词。")
HARD = ("【逐条落实】大纲里的每个信息点都要落到正文，包括人物的回忆与联想，不得遗漏。"
        "【不得增删】不得新增大纲之外的转折或结局，不得编造原文没有的动作。"
        "【禁解剖心理】不得出现人物自我解说式的心理分析（如“这个不重要，重要的是…”）。"
        "【细节自生】环境、光影、声音、气味等细节须自行铺陈，不得只把大纲的用词换个说法。")

LEAD_INPUT = [   # 大纲在 input 字段
    "请根据以下剧情大纲，撰写一段小说正文。",
    "根据下面的剧情大纲写一段小说正文。",
    "这是一段剧情大纲，请把它写成小说正文。",
    "把下面这段剧情扩写为小说正文片段。",
    "依据以下剧情大纲，撰写小说正文。",
    "以下是一条剧情大纲，请据此产出小说正文。",
    "请按下面的剧情写一段小说。",
    "剧情大纲如下，请撰写小说正文。",
]
LEAD_INLINE = [  # 大纲内联进 instruction
    "剧情：{outline}\n请据此写一段小说正文。",
    "写一段小说正文。剧情：{outline}。",
]
ALL = [(v, False) for v in LEAD_INPUT] + [(v, True) for v in LEAD_INLINE]


def pick(sid, n):
    return int(hashlib.md5(sid.encode('utf-8')).hexdigest(), 16) % n


def main():
    src = [json.loads(l) for l in open(SRC, encoding='utf-8')]
    out, dist = [], {}
    for r in src:
        sid = r['metadata']['segment_id']
        lead, inline = ALL[pick(sid, len(ALL))]
        ins = f"{lead}要求：{STYLE}{HARD}"
        if inline:
            ins = f"{lead.format(outline=r['input'])}要求：{STYLE}{HARD}"
            inp = ""
        else:
            inp = r['input']
        out.append({"instruction": ins, "input": inp, "output": r['output'], "metadata": r['metadata']})
        dist[lead[:20]] = dist.get(lead[:20], 0) + 1

    with open(DST, 'w', encoding='utf-8') as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'已写出 {DST}（{len(out)} 条，{len(ALL)} 种指令 × 4 条硬约束）')
    print('平均 instruction 长度:', sum(len(r['instruction']) for r in out) // len(out), '字')


if __name__ == '__main__':
    main()
