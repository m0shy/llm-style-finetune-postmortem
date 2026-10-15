# -*- coding: utf-8 -*-
"""结构化大纲数据集 —— 让训练输入与真实推理格式对齐

为什么必须做：
  推理端 outline_expand.py 发出的 prompt 是「本次要写（章级大纲）+ 后文走向 + 硬约束」，
  而既有 396 条大纲式样本的输入只有一句剧情骨架、没有后文。
  两者结构不一致 => 模型会把真实 prompt 当分布外，写出跟后文打架的内容。
  本脚本用样本自带的 segment_id / scene_id 顺序，自动补出「后文走向」段，并统一指令。

用法：python scripts/build_outline_structured.py
输出：data_dual/dataset_outline_structured.jsonl
"""
import json, os, re, sys, io, collections

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 单一事实来源：指令必须与推理端完全一致，否则就是 train != inference
from outline_expand import SYS_RULES      # noqa: E402

DS = r'<项目目录>\Datasets'
SRC = os.path.join(DS, 'data_dual', 'dataset_outline_norm.jsonl')
OUT = os.path.join(DS, 'data_dual', 'dataset_outline_structured.jsonl')

PLACEHOLDER = '（本题为独立场景，无可用的后文摘要；请只把这一幕写完整，不要外推后续剧情）'


def key_of(m):
    """返回 (排序键, 定位标签)。"""
    sid = m.get('segment_id') or m.get('scene_id') or ''
    mt = re.match(r'^([A-Z]+)-(\d+)-(\d+)$', sid)
    if mt:
        return (int(mt.group(2)), int(mt.group(3))), sid
    ch = m.get('chapter') or m.get('source_position') or ''
    mc = re.search(r'(\d+)', str(ch))
    return (int(mc.group(1)) if mc else 0, 0), str(ch)


def main():
    rows = [json.loads(l) for l in open(SRC, encoding='utf-8') if l.strip()]
    # 分两种来源各自排序（片段级/场景级混排会错乱）
    groups = collections.defaultdict(list)
    for i, r in enumerate(rows):
        m = r['metadata']
        fam = 'SEG' if m.get('segment_id') else 'SCN'
        k, lab = key_of(m)
        groups[fam].append((k, i, lab))
    order = {}                    # 全局序 -> 后续条目（跨章取，章末也能拿到后文）
    for fam, items in groups.items():
        items.sort()
        for pos, (k, gi, lab) in enumerate(items):
            order[gi] = (fam, k, lab, [g[1] for g in items[pos + 1:pos + 3]])

    out = []
    for gi, r in enumerate(rows):
        fam, k, lab, nxt_idx = order[gi]
        parts = []
        for j in nxt_idx:
            sk = rows[j]['input'].strip().replace('\n', ' ')
            parts.append(sk[:220])
        nxt = '\n'.join(f'{i+1}. {p}' for i, p in enumerate(parts)) if parts else PLACEHOLDER
        # ⚠️ 这里必须与**推理端 build_prompt 的措辞逐字对齐**。
        # 之前训练端写的是「剧情大纲：」+「第15章的这一幕（定位 SEG-0015-01）」，
        # 而推理端写的是「章级大纲：」+「《第二卷》第3章（本次只写这一幕的第 1/1 段…）」，
        # 同一个槽位用了不同标签 —— 这正是 v5 那次"模型直接忽略某个 section"的成因。
        inp = (f'==== 本次要写 ====\n'
               f'《灵境行者》第{k[0]}章（本次只写这一幕的第 1/1 段，不要写完整章）\n'
               f'章级大纲：{r["input"].strip()}\n'
               f'本章爽点闭环：（见章级大纲）\n\n'
               f'==== 后文走向（仅供对齐，严禁提前写出）====\n'
               f'{nxt}\n\n'
               f'请写出这一幕的正文。')
        out.append({
            'instruction': SYS_RULES,
            'input': inp,
            'output': r['output'],
            'metadata': {'task': 'outline', 'book': '灵境行者',
                         'chapter': str(k[0]), 'loc': lab, 'family': fam},
        })

    with open(OUT, 'w', encoding='utf-8') as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    withn = sum(1 for r in out if PLACEHOLDER not in r['input'])
    print(f'结构化大纲样本 {len(out)} 条 -> {OUT}')
    print(f'  含真实后文 {withn} 条 / 占位 {len(out) - withn} 条')
    print(f'  input 平均长度 {sum(len(r["input"]) for r in out)//len(out)} 字')
    for r in out[:2]:
        print('\n----- 示例 -----')
        print(r['input'][:420])


if __name__ == '__main__':
    main()
