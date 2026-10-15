# -*- coding: utf-8 -*-
"""重造 SFT 数据：长度可控版（2026-09-19）。

核心思想：
  旧数据只有一种模式：「~1000 字大纲 → 3000~4000 字正文」✗
  模型学不到"听字数指令" ✗

新数据：五个长度档，每档从卖报亲笔原文里切对应大小的片段 ✓
  300 字档：切 ~350 字片段 → 大纲抽 ~50 字   + 指令"写约 300 字"
  800 字档：切 ~900 字片段 → 大纲抽 ~150 字  + 指令"写约 800 字"
  1500 字档：切 ~1600 字 → 大纲 ~300 字      + 指令"写约 1500 字"
  3000 字档：切 ~3200 字 → 大纲 ~600 字      + 指令"写约 3000 字"
  4500 字档：切 ~4800 字 → 大纲 ~900 字      + 指令"写约 4500 字"

  大纲 = 该片段的句子均匀采样（保持原文顺序 ✓ 零编造 ✓✓）

混合：旧 SFT 数据保留一部分（能力不丢 ✓）
"""
import os
import re
import sys
import json
import random
import collections

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

SRC_DIR = r'<项目目录>\Datasets\语料_清洗后'
OUT = r'<项目目录>\LLaMA-Factory\data\dataset_lenctl_v1.jsonl'
OLD = r'<项目目录>\LLaMA-Factory\data\dataset_multi_v25_flat2.jsonl'

BAIBAO = [
    'clean_灵境行者(1-500章).txt',
    'clean_灵境行者(501-1000章).txt',
    'clean_灵境行者(1001-1050章).txt',
    'clean__全本合并.txt',
    'clean_我的姐姐是大明星.txt',
    'clean_原来我是妖二代.txt',
]

# 长度档：目标字数 → (切片长, 大纲字数, 每档条数上限)
TIERS = {
    300:  (360, 55, 600),
    800:  (900, 150, 600),
    1500: (1650, 300, 500),
    3000: (3250, 620, 400),
    4500: (4900, 920, 300),
}

random.seed(20260919)

INSTR_HEAD = None  # 运行时从 serve_chapter_api.py 读


def load_instruction():
    global INSTR_HEAD
    s = open(r'<项目目录>\Datasets\scripts\serve_chapter_api.py', encoding='utf-8').read()
    i = s.find('INSTRUCTION = """') + len('INSTRUCTION = """')
    j = s.find('"""', i)
    head = s[i:j]
    # 把末尾的【输出】规则替换成长度可控版
    head = re.sub(r'【输出】[^\n]*',
                  '【输出】只输出正文。**绝对不要输出标题、章节号、字数统计、时间戳、分隔线或任何标记**，直接以下一个自然段开始。',
                  head)
    INSTR_HEAD = head


def 抽大纲(text, target):
    """从片段里均匀抽句子，拼成约 target 字的大纲。"""
    sents = [s.strip() for s in re.split(r'(?<=[。！？])', text) if s.strip()]
    if not sents:
        return ''
    # 先粗切：直接连句子到目标长度
    buf, out, i = 0, [], 0
    step = max(1, len(sents) // max(2, int(target / 40) + 2))
    while i < len(sents) and buf < target:
        out.append(sents[i])
        buf += len(sents[i])
        i += step
    return ''.join(out)


def main():
    load_instruction()
    assert INSTR_HEAD, '读不到写作规则 ✗'
    names = open(r'<项目目录>\Datasets\names\自创作品_专名.txt', encoding='utf-8').read().strip()
    BOOK = '自创作品'

    per_tier = collections.Counter()
    records = []
    for name in BAIBAO:
        p = os.path.join(SRC_DIR, name)
        if not os.path.exists(p):
            continue
        text = open(p, encoding='utf-8').read()
        print('  处理 %s（%d 字）' % (name, len(text)))

        for goal, (seglen, outlen, cap) in TIERS.items():
            # 按目标切片（不重叠，跨整本书滑动 ✓）
            pos, made = 0, 0
            while pos + seglen < len(text) and made < cap // 6:   # 每本书上限 = 档位上限/6
                seg = text[pos:pos + seglen]
                # 只在句子边界切
                m = None
                for m in re.finditer(r'[。！？]', seg[seglen - 200:] if seglen > 200 else seg):
                    pass
                if m:
                    seg = seg[:seglen - 200 + m.end()] if seglen > 200 else seg[:m.end()]
                if len(seg) < seglen * 0.6:
                    pos += seglen; continue
                outline = 抽大纲(seg, outlen)
                if len(outline) < outlen * 0.35:      # 大纲太短说明这段句子稀疏，跳过
                    pos += seglen; continue
                instr = INSTR_HEAD + (
                    '\n\n【本次要求】把上面的大纲扩写成一段连贯正文。'
                    f'**目标长度约 {goal} 字**（允许上下浮动一成半）。'
                    '宁可在细节上多铺陈，也不要提前收尾。')
                inp = (names + '\n\n==== 本次要写 ====\n'
                       + f'章级大纲（{len(outline)} 字）：{outline}\n'
                       + '本章爽点闭环：（见章级大纲）\n')
                records.append({'instruction': instr, 'input': inp, 'output': seg.strip()})
                per_tier[goal] += 1
                made += 1
                pos += len(seg)
    print()
    print('=== 各档产出 ===')
    for goal in sorted(TIERS):
        print('  %5d 字档：%5d 条' % (goal, per_tier[goal]))
    total_new = len(records)
    print('  新数据合计: %d 条' % total_new)

    # 混入旧数据的一部分（保留旧能力 ✓）
    old = [json.loads(l) for l in open(OLD, encoding='utf-8') if l.strip()]
    random.shuffle(old)
    keep_old = old[:2500]
    print('  旧数据保留: %d 条' % len(keep_old))
    records.extend(keep_old)
    random.shuffle(records)

    with open(OUT, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('  写出 %s（%d 条）' % (OUT, len(records)))


if __name__ == '__main__':
    main()
