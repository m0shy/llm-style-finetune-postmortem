# -*- coding: utf-8 -*-
"""大纲式样本「格式归一化」——修复 instruction/input 错位的 47 条

问题（体检发现）：
  一部分大纲式样本把剧情塞进了 instruction（形如「剧情：……」或「写一段小说正文。剧情：……」），
  input 为空；另一部分（绝大多数）则是 instruction = 通用写作要求，input = 剧情骨架。
  同一种任务出现两套输入范式，会让模型学到互相打架的 prompt 结构。

修复策略：
  统一为 instruction = 通用写作要求（随机取变体），input = 剧情骨架。
  剧情从原 instruction 里「剧情：」之后截出；若原本 input 非空则原样保留。

用法：python scripts/normalize_outline.py
输出：data_dual/dataset_outline_norm.jsonl
"""
import json, os, re, sys, io, random, hashlib

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass
SRC = r'<项目目录>\Datasets\data_dual\dataset_dual.jsonl'
OUT = r'<项目目录>\Datasets\data_dual\dataset_outline_norm.jsonl'

TEMPLATES = [
    "这是一段剧情大纲，请把它写成小说正文。要求：画面感强、节奏张弛有度，长短句交错；"
    "注重感官描写（视觉/听觉/触觉）；用具体的动作和微表情展现人物心理，不要直接陈述情绪。",
    "把下面这段剧情扩写为小说正文片段。要求：画面感强、节奏张弛有度，长短句交错；"
    "注重感官描写（视觉/听觉/触觉）；用具体的动作和微表情展现人物心理，不要直接陈述情绪。",
    "请根据以下剧情大纲，撰写一段小说正文。要求：画面感强、节奏张弛有度，长短句交错；"
    "注重感官描写（视觉/听觉/触觉）；用具体的动作和微表情展现人物心理，不要直接陈述情绪。",
    "这是一段剧情骨架，请把它写成一个有头有尾的场景。要求：画面感强、节奏张弛有度，长短句交错；"
    "注重感官描写（视觉/听觉/触觉）；用具体的动作和微表情展现人物心理，不要直接陈述情绪。",
    "剧情大纲如下，请撰写小说正文。要求：画面感强、节奏张弛有度，长短句交错；"
    "注重感官描写（视觉/听觉/触觉）；用具体的动作和微表情展现人物心理，不要直接陈述情绪。",
    "根据下面的剧情大纲写一段小说正文。要求：画面感强、节奏张弛有度，长短句交错；"
    "注重感官描写（视觉/听觉/触觉）；用具体的动作和微表情展现人物心理，不要直接陈述情绪。",
    "依据以下剧情骨架，撰写场景正文（要有开端、推进与收束）。要求：画面感强、节奏张弛有度，长短句交错；"
    "注重感官描写（视觉/听觉/触觉）；用具体的动作和微表情展现人物心理，不要直接陈述情绪。",
    "请按下面的剧情骨架写一个完整场景。要求：画面感强、节奏张弛有度，长短句交错；"
    "注重感官描写（视觉/听觉/触觉）；用具体的动作和微表情展现人物心理，不要直接陈述情绪。",
]


def pick(seed_text):
    h = int(hashlib.md5(seed_text.encode('utf-8')).hexdigest(), 16)
    return TEMPLATES[h % len(TEMPLATES)]


def main():
    rows = [json.loads(l) for l in open(SRC, encoding='utf-8') if l.strip()]
    fixed, kept, other = [], 0, []
    for r in rows:
        if r.get('metadata', {}).get('task') != 'outline':
            other.append(r)
            continue
        ins, inp = r.get('instruction', ''), r.get('input', '')
        if '剧情：' in ins:
            plot = ins.split('剧情：', 1)[1].strip()
            base = (inp.strip() + '\n' + plot).strip() if inp.strip() else plot
            r = dict(r)
            r['instruction'] = pick(base)
            r['input'] = base
            fixed.append(r)
        else:
            kept += 1
            if not inp.strip():
                other.append(r)          # 少数脏数据，放回但不参与
            else:
                fixed.append(r)
    with open(OUT, 'w', encoding='utf-8') as f:
        for r in fixed:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'归一化完成：修复错位 {len(fixed) - kept} 条 / 原本规范 {kept} 条 -> 共 {len(fixed)} 条')
    print(f'  非大纲式（续写等）{len(other)} 条未写入本文件')
    # 自检
    bad = [r for r in fixed if not r['input'].strip() or '剧情：' in r['instruction']]
    print(f'  自检：残留错位 {len(bad)} 条')


if __name__ == '__main__':
    main()
