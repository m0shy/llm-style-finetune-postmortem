# -*- coding: utf-8 -*-
"""筛选优质场景：目标 2000 个（灵境行者优先 ✓ 文风最接近目标 ✓）"""
import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

SRC = r'<项目目录>\LLaMA-Factory\data\scenes_v1.jsonl'
OUT = r'<项目目录>\LLaMA-Factory\data\scenes_selected.jsonl'

# 筛选规则
MIN, MAX = 800, 2000          # 单次扩写的黄金区间 ✓
排除 = ['第223章', '第46章', '第9章']  # 章标题残留（清洗漏网 ✗ 抽检发现的 ✗）
章标题 = re.compile(r'第[0-9一二三四五六七八九十百千]+章')


def main():
    rows = [json.loads(l) for l in open(SRC, encoding='utf-8') if l.strip()]
    # 灵境行者优先（文风目标 ✓）→ 全收
    # 大奉/姐姐/妖二代 → 补充到 2000
    lingjing = [r for r in rows if '灵境' in r['book']
                and MIN <= len(r['text']) <= MAX
                and not 章标题.search(r['text'][:50])]
    others = [r for r in rows if '灵境' not in r['book']
              and MIN <= len(r['text']) <= MAX
              and not 章标题.search(r['text'][:50])]

    selected = lingjing[:]                    # 灵境全收 ✓
    need = 2000 - len(selected)
    if need > 0:
        selected.extend(others[:need])        # 其他书补足 ✓

    with open(OUT, 'w', encoding='utf-8') as f:
        for r in selected:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    import collections
    c = collections.Counter(r['book'] for r in selected)
    print('  筛选结果: %d / %d' % (len(selected), len(rows)))
    for k, v in c.most_common():
        print('    %-28s %5d' % (k, v))
    ls = sorted(len(r['text']) for r in selected)
    print('  长度: %d ~ %d（中位 %d）' % (ls[0], ls[-1], ls[len(ls)//2]))


if __name__ == '__main__':
    main()
