# -*- coding: utf-8 -*-
"""按新配比构建 CPT 语料（卖报主导 80% / 其他作者精选 20%）。

输入：语料_清洗后/ 目录里的 clean_*.txt
输出：cpt_corpus_v3.jsonl（切块 ≈ 900~1100 字/块，与旧语料对齐 ✓）

配比规则（2026-09-19 用户裁定）：
  卖报亲笔 4 本：全部泡进去（灵境行者/大奉打更人/原来我是妖二代/我的姐姐是大明星）
  其他作者：按题材精选 + 切断采样到配额（20%）
    ✓ 我有一座恐怖屋 / 惊悚乐园 / 这游戏也太真实了 / 还剩三个月命 / 生活系游戏
    ✗ 全职高手（电竞题材远）/ 轮回乐园、超神机械师大部头（面板流稀释卖报味）
"""
import os, re, sys, json, glob, random, collections

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

SRC = r'<项目目录>\Datasets\语料_清洗后'
OUT = r'<项目目录>\LLaMA-Factory\data\cpt_corpus_v3.jsonl'

BAIBAO = [  # 卖报亲笔：全量
    'clean_灵境行者(1-500章).txt',
    'clean_灵境行者(501-1000章).txt',
    'clean_灵境行者(1001-1050章).txt',
    'clean__全本合并.txt',
    'clean_我的姐姐是大明星.txt',
    'clean_原来我是妖二代.txt',
]
OTHER_QUOTA = 3_100_000  # 其他作者总配额（字），约 20%
OTHER_BOOKS = {          # 其他作者：精选 + 每本配额上限（字）
    'clean_我有一座恐怖屋.txt': 1_200_000,
    'clean_惊悚乐园_1-500章.txt': 700_000,
    'clean_这游戏也太真实了_501-1000章.txt': 700_000,
    'clean_还剩三个月命，请让我从容赴死.txt': 180_000,
    'clean_生活系游戏.txt': 400_000,
}

CHUNK = 1000     # 目标块长（字符）
OVER = 60        # 允许超出
_MIN = 200       # 太短的尾块丢弃
random.seed(20260919)


def chunks_of(text, chunk=CHUNK, over=OVER, min_len=_MIN):
    paras = [p.strip() for p in text.split('\n') if p.strip()]
    buf, out = '', []
    for p in paras:
        if len(buf) + len(p) > chunk + over and len(buf) >= min_len:
            out.append(buf)
            buf = p
        else:
            buf = (buf + '\n' + p).strip()
    if len(buf) >= min_len:
        out.append(buf)
    return out


def main():
    stats = collections.Counter()
    baibao_chunks, other_chunks = [], []
    print('=' * 64)
    print('① 卖报亲笔（全量）')
    for name in BAIBAO:
        p = os.path.join(SRC, name)
        if not os.path.exists(p):
            print('  ✗ 缺', name); continue
        txt = open(p, encoding='utf-8').read()
        cs = chunks_of(txt)
        baibao_chunks.extend(cs)
        print('  ✅ %-34s %7d 万字 → %5d 块' % (name, len(txt)//10000, len(cs)))
    print()
    print('② 其他作者（切断采样到配额 %d 万字）' % (OTHER_QUOTA//10000))
    for name, quota in OTHER_BOOKS.items():
        p = os.path.join(SRC, name)
        if not os.path.exists(p):
            print('  ✗ 缺', name); continue
        txt = open(p, encoding='utf-8').read()
        cs = chunks_of(txt)
        # 均匀切断：按配额/总量的比例取块
        keep = min(len(cs), max(1, int(len(cs) * quota / max(1, len(txt)))))
        step = len(cs) / keep
        picked = [cs[int(i * step)] for i in range(keep)]
        other_chunks.extend(picked)
        print('  ✅ %-44s %7d 万字 → 取 %5d 块（%d 万字）' % (
            name, len(txt)//10000, len(picked), sum(len(c) for c in picked)//10000))

    print()
    print('③ 配比核对')
    b = sum(len(c) for c in baibao_chunks)
    o = sum(len(c) for c in other_chunks)
    print('  卖报亲笔: %d 万字（%.1f%%）' % (b//10000, 100*b/(b+o)))
    print('  其他作者: %d 万字（%.1f%%）' % (o//10000, 100*o/(b+o)))
    print('  合计:     %d 万字' % ((b+o)//10000))

    allc = baibao_chunks + other_chunks
    random.shuffle(allc)
    with open(OUT, 'w', encoding='utf-8') as f:
        for c in allc:
            f.write(json.dumps({'text': c}, ensure_ascii=False) + '\n')
    print()
    print('④ 写出 %s' % OUT)
    print('   %d 块 / 合计 %d 万字' % (len(allc), sum(len(c) for c in allc)//10000))


if __name__ == '__main__':
    main()
