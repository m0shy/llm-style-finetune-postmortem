# -*- coding: utf-8 -*-
"""长大纲探针 —— 用**源书素材**造一份 800~1000 字的章级大纲，再拿它测模型

为什么需要（两个问题一起解决）：
  1. **输入粒度不对**：此前探针喂给模型的"章级大纲"只有约 100 字
     （来自 outline_lib 的 U 章节摘要），而用户实际会写 **800~1000 字**。
     给的引导少一个数量级 → 模型只能自己发挥 → **此前所有测量都偏悲观**。
  2. **不能用用户的素材**：用户 2026-09-15 再次强调他的细纲/大纲尚未完成、
     不能用于训练；为稳妥起见，**探针输入也不用他的东西**。

做法：取灵境同一章里 5~7 个连续场景骨架（SEG skeleton）拼成约 800~1000 字的章级大纲，
      走与正常生成完全相同的 build_prompt，再跑 ai_tells 检测。

用法：
  python scripts/probe_long_outline.py --adapter <路径> --chapter 15 --n 3 --label v18L
  python scripts/probe_long_outline.py --chapter 15 --dry-run      # 只看造出来的大纲
"""
import os, sys, argparse, json, collections, re

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DS = r'<项目目录>\Datasets'
SRC = os.path.join(DS, 'data_dual', 'dataset_outline_norm.jsonl')


def segs_by_chapter():
    seg = collections.defaultdict(dict)
    for l in open(SRC, encoding='utf-8'):
        if not l.strip():
            continue
        r = json.loads(l)
        m = re.match(r'^SEG-(\d+)-(\d+)$', r['metadata'].get('segment_id') or '')
        if m:
            seg[int(m.group(1))][int(m.group(2))] = r
    return seg


def build_long_outline(seg, chapter, lo=800, hi=1000):
    """把同一章的连续场景骨架拼成 800~1000 字的章级大纲。

    不编造任何内容 —— 只用源书里已有的场景骨架原文，只是把它们按顺序接起来。
    """
    rows = seg.get(chapter) or {}
    idx = sorted(rows)
    if not idx:
        return None
    parts, total = [], 0
    for i in idx:
        sk = re.split(r'请据此|要求：', rows[i]['input'])[0].strip()
        sk = sk.replace('\n', ' ')
        parts.append(sk)
        total += len(sk)
        if total >= hi:
            break
    txt = '；'.join(parts)
    return txt[:hi] if txt else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--adapter')
    ap.add_argument('--chapter', type=int, default=None, help='灵境章号；不给就自动挑场景最多的')
    ap.add_argument('--n', type=int, default=3)
    ap.add_argument('--label', default='long')
    ap.add_argument('--max-new', type=int, default=2400, help='默认 2400 token ≈ 3500 字（对准 3000~4000 字目标）')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    seg = segs_by_chapter()
    # 场景最多的章最适合拼长大纲
    if a.chapter is None:
        a.chapter = max(seg, key=lambda c: len(seg[c]))
    ol = build_long_outline(seg, a.chapter)
    if not ol:
        print(f'第 {a.chapter} 章没有场景骨架，换一章。')
        return
    print(f'[长大纲] 用灵境第 {a.chapter} 章的 {len(seg[a.chapter])} 个场景骨架拼出 '
          f'**{len(ol)} 字**章级大纲（用户实际会写 800~1000 字）')
    print('--- 大纲前 300 字 ---')
    print(ol[:300])
    if a.dry_run:
        return

    from outline_expand import SYS_RULES
    from probe_one import load_model, run
    from ai_tells import metrics

    prompt = (f'{SYS_RULES}\n\n'
              f'==== 本次要写 ====\n《灵境行者》第{a.chapter}章（本次只写这一幕的第 1/1 段，不要写完整章）\n'
              f'章级大纲：{ol}\n本章爽点闭环：（见章级大纲）\n\n'
              f'请写出这一幕的正文。')
    print(f'[长大纲] prompt {len(prompt)} 字 | 采样 {a.n} 次 | max_new {a.max_new} token')
    model, tok = load_model(a.adapter)
    texts = []
    for i in range(a.n):
        t = run(model, tok, prompt, a.max_new)
        texts.append(t)
        print(f'  第{i+1}次: {len(t)} 字')

    merged = '\n\n'.join(texts)
    m = metrics(merged)
    print(f'\n[长大纲] ===== 结果（{len(merged)} 字 / {a.n} 次）=====')
    print(f'  字均 {len(merged)/a.n:.0f} 字  ← 目标 3000~4000')
    for k in ['AI指纹词 每千字', '情绪词 每千字', '最长连续同构句', '段落长度方差', '对话占比%', '感官/闲笔 每千字']:
        print(f'  {k:<18}{m[k]}')
    print('  卖报基准   指纹词1.5 情绪0.5 同构4 方差272 对话23.5% 感官1.1')
    dump = os.path.join(r'<项目目录>\LLaMA-Factory\outputs', f'long_{a.label}.json')
    json.dump({'label': a.label, 'chapter': a.chapter, 'outline': ol,
               'samples': texts, 'metrics': m}, open(dump, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'  已落盘 {dump}')


if __name__ == '__main__':
    main()
