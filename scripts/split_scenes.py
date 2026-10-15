# -*- coding: utf-8 -*-
"""场景级切分 v1（2026-09-24）：把卖报原文切成"叙事单元"，取代任意字数切片。

切分规则（规则版 v1 ✓ 人工抽检兜底 ✓）：
  ① 章边界：第X章 标题行
  ② 场景边界（章内）：命中任一强制断点 → 新场景
     - 时间跳转词：第二天|次日|当晚|深夜|回到家|回到|回到宿舍|翌日|第二天早上|一个小时后|半小时后
     - 空间跳转词：来到|走进|回到|赶到 + 新地点（限制：行首）
     - 连续空行 ≥2
  ③ 尺寸门控：<300 字丢弃 ✗ / >2200 字再按中点二分 ✓
产出：scenes.jsonl（book 源 / 章号 / 场景序号 / 正文）
"""
import os
import re
import sys
import json
import glob
import collections

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

SRC = r'<项目目录>\Datasets\语料_清洗后'
OUT = r'<项目目录>\LLaMA-Factory\data\scenes_v1.jsonl'

BAIBAO = [
    'clean_灵境行者(1-500章).txt',
    'clean_灵境行者(501-1000章).txt',
    'clean_灵境行者(1001-1050章).txt',
    'clean__全本合并.txt',
    'clean_我的姐姐是大明星.txt',
    'clean_原来我是妖二代.txt',
]

时间词 = re.compile(r'^(第二天|次日|翌日|当晚|当天晚上|深夜|凌晨|一个小时后|半小时后|几分钟后|第二天早上|第二天下午|次日清晨|晚饭后|午后|傍晚)')
空间词 = re.compile(r'^(他|她|林|叶|陈|楚|杜|方|萧|苏)[^，。]{0,10}(回到|来到|走进|赶到|返回|踏入)')

MIN_LEN, MAX_LEN = 300, 2200


def split_scenes(text):
    # 章边界
    chapters = re.split(r'\n(?=第[0-9一二三四五六七八九十百千]+章)', text)
    scenes = []
    for ch in chapters:
        ch = ch.strip()
        if len(ch) < MIN_LEN:
            continue
        # 章内：按空行聚段
        paras = [p.strip() for p in re.split(r'\n\s*\n', ch) if p.strip()]
        cur, cur_len = [], 0
        scenes_in_ch = []

        def flush():
            nonlocal cur, cur_len
            if cur and cur_len >= 120:
                scenes_in_ch.append('\n\n'.join(cur))
            cur, cur_len = [], 0

        for p in paras:
            # 强制断点判定（段首）
            brk = bool(时间词.match(p) or 空间词.match(p))
            if brk and cur_len >= MIN_LEN:
                flush()
            cur.append(p)
            cur_len += len(p)
            if cur_len >= MAX_LEN:
                flush()
        flush()
        # 尺寸门控
        for s in scenes_in_ch:
            if len(s) < MIN_LEN:
                continue
            while len(s) > 2600:      # 超长切分：优先按空行，无空行则按句号硬切 ✗（修复死循环 ✓）
                paras2 = [x for x in s.split('\n\n') if x.strip()]
                if len(paras2) >= 2:
                    mid = len(paras2) // 2
                    s1, s2 = '\n\n'.join(paras2[:mid]), '\n\n'.join(paras2[mid:])
                else:
                    # 无空行：按句号硬切一半 ✓
                    sents = re.split(r'(?<=[。！？”])', s)
                    mid = max(1, len(sents) // 2)
                    s1, s2 = ''.join(sents[:mid]), ''.join(sents[mid:])
                if len(s1) >= MIN_LEN:
                    scenes.append(s1)
                if len(s2) <= 2600:
                    s = s2
                    break
                s = s2
            if len(s) >= MIN_LEN:
                scenes.append(s)
    return scenes


def main():
    total = 0
    stats = collections.Counter()
    with open(OUT, 'w', encoding='utf-8') as f:
        for name in BAIBAO:
            p = os.path.join(SRC, name)
            if not os.path.exists(p):
                print('  ✗ 缺', name)
                continue
            text = open(p, encoding='utf-8').read()
            scenes = split_scenes(text)
            book = name.replace('clean_', '').replace('.txt', '')
            for i, s in enumerate(scenes):
                f.write(json.dumps({'book': book, 'scene_id': i, 'text': s},
                                   ensure_ascii=False) + '\n')
            total += len(scenes)
            stats[book] = len(scenes)
            print('  ✅ %-30s %5d 场景' % (book, len(scenes)))
    print()
    print('  合计: %d 个场景 → %s' % (total, OUT))
    # 长度分布抽查
    import random
    random.seed(1)
    sample = [json.loads(l) for l in open(OUT, encoding='utf-8')]
    random.shuffle(sample)
    for s in sample[:3]:
        print('  --- [%s#%d %d 字] %s' % (s['book'], s['scene_id'], len(s['text']),
                                          s['text'][:70].replace('\n', ' ')))


if __name__ == '__main__':
    main()
