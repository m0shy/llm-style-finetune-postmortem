# -*- coding: utf-8 -*-
"""使用逻辑检测 —— 修辞/情绪的**落点形态**，不是均值

为什么需要（用户 2026-09-15 的洞察）：
  "现在你的判断全是依照句式结构来的，但是句式结构是正确的，很多著名作家都会用，
   区别在于 AI 的使用逻辑和人类的使用逻辑不一样，所以会导致很多 AI 味道。"
  —— 说得对。长短句、比喻、情绪，名家都在用；**AI 味不在"用了什么"，在"怎么用"。**

  我此前全在测**均值**（每千字几个比喻、几个情绪词）。但均值相同，用法可以完全相反：
      卖报写一场戏：比喻 0 个，某个关键句连用 3 个        → 均值低，但**有脉冲**
      AI 写同一场戏：每段均匀 1 个                        → 均值也可能 0.7，但**均匀铺开**
  均值分不出来，**分布形态分得出来**。

  文献把这件事叫 burstiness（突发性）："人类写作变化更多、不可预测；AI 过于平滑均匀"。
  我只测了它在句式上的表现（句长波动/段长波动），**没测它在修辞落点上的表现** —— 这个脚本补的就是这块。

三个指标：
  1. **留白率**   完全没有修辞/情绪的小段占比。人类高（多数段落干干净净，只在关键处发力）；
                  AI 低（每段都要意思一下）。**这一项最直观。**
  2. **落点方差** 各小段修辞数的方差。人类大（有的 0、有的 3）；AI 小。
  3. **峰值倍数** 最密的那一段 ÷ 全篇平均。人类能有 5~10 倍；AI 通常 2~3 倍。

用法：
  python scripts/burstiness.py 稿件.md
  python scripts/burstiness.py 产出目录/
  python scripts/burstiness.py --baseline       # 只看卖报原著基准
"""
import os, sys, re, glob, statistics, argparse

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from style_gap import EMO, SIM, FILLER, GRAND   # noqa: E402

DEV = list(EMO) + list(SIM) + list(GRAND)       # 修辞/情绪（不含连接词 —— 连接词是逻辑层，另算）
BLOCK = 200                                     # 每个"小段"的字数


def read_any(p):
    if os.path.isdir(p):
        return ''.join(read_any(f) for f in sorted(glob.glob(os.path.join(p, '*.md')))
                       + sorted(glob.glob(os.path.join(p, '*.txt'))))
    for enc in ('utf-8', 'gbk'):
        try:
            return __import__('scan_noise').read_text(p)   # 2026-09-16 统一修缮：原 errors='ignore' 对 GBK 静默出错
        except Exception:
            continue
    return ''


def burst(text, block=BLOCK):
    """把文本切成 block 字的小段，数每段的修辞/情绪词，看落点形态。"""
    t = re.sub(r'\s+', '', text)
    blocks = [t[i:i + block] for i in range(0, len(t), block)]
    blocks = [b for b in blocks if len(b) >= block * 0.6]     # 丢掉尾部残块
    if len(blocks) < 5:
        return None
    counts = [sum(b.count(w) for w in DEV) for b in blocks]
    tot = sum(counts)
    n = len(counts)
    mean = tot / n
    zero = sum(1 for c in counts if c == 0) / n * 100
    var = statistics.pvariance(counts)
    peak = (max(counts) / mean) if mean > 0 else 0
    # 聚集度：最密的 10% 小段承载了多少比例的全部修辞（人类会更集中）
    k = max(1, int(n * 0.1))
    top_share = sum(sorted(counts, reverse=True)[:k]) / tot * 100 if tot else 0
    return {
        '小段数': n, '总量': tot, '均值/段': round(mean, 2),
        '留白率%': round(zero, 1), '落点方差': round(var, 2),
        '峰值倍数': round(peak, 1), '前10%段落承载%': round(top_share, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', nargs='?')
    ap.add_argument('--baseline', action='store_true')
    a = ap.parse_args()

    MAIBAO = [r'<old-lib>\《灵境行者》\灵境行者(1-500章).txt',
              r'<old-lib>\《灵境行者》\灵境行者(501-1000章).txt',
              r'<old-lib>\《大奉打更人》\大奉打更人(1-500章).txt',
              r'<old-lib>\《大奉打更人》\大奉打更人(501-955章).txt']
    base = ''.join(read_any(p) for p in MAIBAO if os.path.isfile(p))
    if not base:
        print('找不到卖报原著')
        return
    # ⚠️ 基准必须与待测文本**样本量对齐**。
    # 踩过：基准取 300 万字、模型产出只有 8600 字，方差类指标在样本量差 350 倍时不可比
    # （小样本方差天然偏高，模型会"看起来更有脉冲"）。这条和"取样范围会改变结论"是同一个坑。
    if a.baseline:
        print('===== 卖报原著基准（使用逻辑）=====')
        for k, v in (bm or {}).items():
            print(f'  {k:<16}{v}')
        return

    t = read_any(a.path)
    if not t:
        print(f'读不到：{a.path}')
        return
    m = burst(t)
    if not m:
        print(f'文本太短（需要 {BLOCK*5} 字以上）')
        return

    # 基准裁到与本文同样长度（同长度才可比）
    want = min(len(t), len(base))
    bm = burst(base[:want])

    print('===== 使用逻辑检测（修辞/情绪的落点形态）=====')
    print(f'对照：卖报原著（截取 {want:,} 字，**与本文等长**）| 本文（{len(t):,} 字）\n')
    print(f'{"指标":<18}{"卖报":>10}{"本文":>10}  说明')
    notes = {
        '留白率%': '越高越像人（多数段落干干净净，只在关键处发力）',
        '落点方差': '越大越像人（有脉冲，不是均匀铺开）',
        '峰值倍数': '越大越像人（最密段 ÷ 平均段）',
        '前10%段落承载%': '越高越像人（修辞集中在少数段落）',
        '均值/段': '均值本身分不出人机 —— 要看上面三项',
    }
    for k in ['留白率%', '落点方差', '峰值倍数', '前10%段落承载%', '均值/段', '小段数']:
        b, v = bm.get(k, 0), m.get(k, 0)
        print(f'{k:<18}{b:>10}{v:>10}  {notes.get(k, "")}')
    print('\n注：这一组测的是"**怎么用**"，与 ai_tells 那组（测"用了多少"）互补。')
    print('    均值相同、用法不同的两段文字，只有这一组能分辨。')


if __name__ == '__main__':
    main()
