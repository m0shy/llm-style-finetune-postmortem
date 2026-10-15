# -*- coding: utf-8 -*-
"""指令多样化器（修复"训练集 228/240 用同一句 instruction"导致的指令绑定塌缩）

输入: dataset_lingjing_final.jsonl（240 条，单一 instruction）
输出: dataset_lingjing_v2.jsonl（同一批数据，指令随机打散为 10 种等价变体）

设计原则:
  1. 移除"多用短句"这类硬约束 —— 它是"碎句/一句一段"的直接诱因，
     改为"长短句交错、节奏张弛"（描述性，不给机械指令）。
  2. 10 种变体等价，按 segment_id 稳定哈希分配（可复现）。
  3. 其中 2 种把大纲"内联"进 instruction（input 置空），
     让模型学会"指令里也可能直接带剧情"，避免只认某一种排布。

用法: python scripts/diversify_instructions.py
"""
import json, os, io, sys, hashlib

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass
BASE = r'<项目目录>\Datasets'
SRC = os.path.join(BASE, 'dataset_lingjing_final.jsonl')
DST = os.path.join(BASE, 'dataset_lingjing_v2.jsonl')
MANIFEST = os.path.join(BASE, '指令变体清单.md')

CORE = ("画面感强、节奏张弛有度，长短句交错；注重感官描写（视觉/听觉/触觉）；"
        "用具体的动作和微表情展现人物心理，不要直接陈述情绪；"
        "禁止使用“首先/其次/总之”等公文连接词。")

# 8 种"大纲放 input 字段"的变体
VARIANTS_INPUT = [
    "请根据以下剧情大纲，撰写一段小说正文。" + CORE,
    "根据下面的剧情写一段小说正文。" + CORE,
    "这是一段剧情大纲，请把它写成小说正文。" + CORE,
    "把下面这段剧情写成小说正文片段。" + CORE,
    "请依据以下剧情扩写小说正文。" + CORE,
    "按下面的剧情，写一段小说。" + CORE,
    "以下是一条剧情大纲，请据此产出小说正文片段。" + CORE,
    "剧情大纲如下，请撰写小说正文。" + CORE,
]

# 2 种"大纲内联进 instruction、input 置空"的变体（模板里用 {outline} 占位）
VARIANTS_INLINE = [
    "剧情：{outline}\n请据此写一段小说正文。" + CORE,
    "写一段小说正文。剧情：{outline}。" + CORE,
]

ALL = [(v, False) for v in VARIANTS_INPUT] + [(v, True) for v in VARIANTS_INLINE]


def pick(sid):
    h = int(hashlib.md5(sid.encode('utf-8')).hexdigest(), 16)
    return h % len(ALL)


def main():
    src = [json.loads(l) for l in open(SRC, encoding='utf-8')]
    out, dist = [], {}
    for r in src:
        sid = r['metadata']['segment_id']
        tpl, inline = ALL[pick(sid)]
        if inline:
            ins, inp = tpl.format(outline=r['input']), ""
        else:
            ins, inp = tpl, r['input']
        out.append({
            "instruction": ins,
            "input": inp,
            "output": r['output'],
            "metadata": r['metadata'],
        })
        dist[tpl[:22]] = dist.get(tpl[:22], 0) + 1

    with open(DST, 'w', encoding='utf-8') as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    lines = ["# 指令变体清单（dataset_lingjing_v2.jsonl）", "",
             f"> 共 {len(out)} 条，打散为 {len(ALL)} 种等价指令，按 segment_id 稳定哈希分配。",
             "> 核心：**移除“多用短句”硬约束**，改为“长短句交错”（避免模型学成碎句）。", "",
             "| # | 指令变体 | 大纲位置 | 分配条数 |", "|---|---|---|---|"]
    for i, (tpl, inline) in enumerate(ALL, 1):
        lines.append(f"| {i} | {tpl[:60].replace('|','/')}… | {'内联 instruction（input 置空）' if inline else 'input 字段'} | {dist.get(tpl[:22],0)} |")
    lines += ["", "## 下一步", "",
              "1. 把 `dataset_lingjing_v2.jsonl` 与通用语料 `general_replay.jsonl` 放进 LLaMA-Factory 的 `data/`。",
              "2. 按 `dataset_info.json` 片段注册两个数据集（见 `llama_factory_qwen2.5_7b_v2.yaml` 文末）。",
              "3. 用 `llama_factory_qwen2.5_7b_v2.yaml` 重训（Epoch 2 / lr 5e-5 / 混 5–10% 通用语料）。"]
    open(MANIFEST, 'w', encoding='utf-8').write('\n'.join(lines))

    print(f'已写出 {DST}（{len(out)} 条）')
    print(f'已写出 {MANIFEST}')
    print('分配统计:')
    for k, v in sorted(dist.items(), key=lambda x: -x[1]):
        print(f'  {v:3d}  {k}…')


if __name__ == '__main__':
    main()
