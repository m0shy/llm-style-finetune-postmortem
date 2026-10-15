# -*- coding: utf-8 -*-
"""风格距离测量 —— 把「像不像卖报」「说没说人话」变成可比的数字

为什么需要：
  「人话」和「卖报腔」一直只能凭感觉判断，导致两个后果：
    ① 模型改好没改好说不清
    ② 我容易拿单条样本下结论（已经栽过一次）
  这个工具把风格拆成若干**可量化轴**，并用卖报原著做基准线，
  于是「差多少」变成一个可以直接看的偏离度。

测的轴（都能用规则算出来，不需要模型）：
  对白占比 / 句长与段长的均值与波动 / 直陈情绪词 / 比喻词 / 套话连接词 /
  升华句 / 四字格 / 用字丰富度 / 句首重复率

用法：
  python scripts/style_gap.py 稿件.md
  python scripts/style_gap.py 章节目录/            # 目录下所有 .md
  python scripts/style_gap.py 稿件.md --baseline   # 顺便打印基准线的原始值
"""
import os, re, sys, json, random, statistics, argparse, collections

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

DS = r'<项目目录>\Datasets'
BASE_CACHE = os.path.join(DS, 'data_dual', 'style_baseline.json')
SRC_HOME = r'<old-lib>'
MAIBAO = [
    os.path.join(SRC_HOME, '《灵境行者》', '灵境行者(1-500章).txt'),
    os.path.join(SRC_HOME, '《大奉打更人》', '大奉打更人(1-500章).txt'),
]

# 直陈情绪：把情绪直接说出来，而不是用动作承载。卖报很少这么写。
EMO = ['心里一暖', '心中一暖', '心里一酸', '心中一酸', '心里一紧', '心中一紧',
       '心里五味杂陈', '内心泛起', '内心涌起', '心中暗道', '感到', '觉得',
       '意识到', '明白了', '他知道', '她知道', '他知道', '心里想', '心中想',
       '心中一喜', '内心充满', '松了一口气', '心中一凛', '心头一热']
# 比喻词：滥用会显得"AI 腔"
SIM = ['仿佛', '宛如', '犹如', '似乎', '像是', '好似', '恍若', '如同']
# 套话连接词
FILLER = ['然而', '于是', '随后', '紧接着', '与此同时', '不由得', '不禁',
          '情不自禁', '下意识', '不由自主', '转眼间', '霎时间', '顷刻间']
# 升华 / 总结句：网文里偶尔用，多了就是"AI 腔"
GRAND = ['这一刻', '此刻', '时间仿佛', '仿佛整个世界', '这，就是', '他知道，这一切',
         '命运的齿轮', '从这一刻起', '谁也没有想到']
QUOTE = re.compile(r'[“"]([^”"]{1,200})[”"]')


def read(p):
    for enc in ('utf-8', 'gbk'):
        try:
            return __import__('scan_noise').read_text(p)   # 2026-09-16 统一修缮：原 errors='ignore' 对 GBK 静默出错
        except Exception:
            continue
    return ''


# 基准块大小。长度敏感指标（用字丰富度）必须在这个长度下比才公平。
BASE_CHUNK = 6000


def metrics(t):
    """把一个文本压成一组可比的数字。"""
    body = re.sub(r'\s+', '', t)
    n = max(len(body), 1)
    sents = [s for s in re.split(r'[。！？…]+', body) if len(s) >= 4]
    paras = [p for p in t.split('\n') if len(p.strip()) >= 10]
    sl = [len(s) for s in sents] or [1]
    pl = [len(p.strip()) for p in paras] or [1]
    dial = sum(len(m.group(1)) for m in QUOTE.finditer(t))
    # 句首重复率：有多少句用同一个两字开头
    heads = [s[:2] for s in sents if len(s) >= 2]
    dup_head = 1 - (len(set(heads)) / max(len(heads), 1))
    return {
        '对白占比%':        round(dial / n * 100, 1),
        '平均句长':          round(statistics.mean(sl), 1),
        '句长波动(标准差)':   round(statistics.pstdev(sl), 1),
        '平均段长':          round(statistics.mean(pl), 1),
        '段长波动(标准差)':   round(statistics.pstdev(pl), 1),
        '直陈情绪 每千字':     round(sum(body.count(w) for w in EMO) / n * 1000, 2),
        '比喻词 每千字':      round(sum(body.count(w) for w in SIM) / n * 1000, 2),
        '套话连接词 每千字':   round(sum(body.count(w) for w in FILLER) / n * 1000, 2),
        '升华句 每千字':      round(sum(body.count(w) for w in GRAND) / n * 1000, 2),
        '用字丰富度%':        round(len(set(body)) / n * 100, 1),
        '句首重复率%':        round(dup_head * 100, 1),
    }


def build_baseline(chunks=80, size=6000):
    """用卖报原著切若干块，算出各指标的平均值当基准线。"""
    if os.path.isfile(BASE_CACHE):
        try:
            return json.load(open(BASE_CACHE, encoding='utf-8'))
        except Exception:
            pass
    pool = []
    for f in MAIBAO:
        t = read(f)
        # 去掉章节标题行、作者的话等
        t = re.sub(r'^\s*第\s*[0-9一二三四五六七八九十百千零两]+\s*[章回].*$', '', t, flags=re.M)
        pool.append(t)
    allm = collections.defaultdict(list)
    random.seed(42)
    for t in pool:
        for _ in range(chunks // len(pool)):
            i = random.randrange(0, max(1, len(t) - size))
            m = metrics(t[i:i + size])
            for k, v in m.items():
                allm[k].append(v)
    # 存**分位数区间**而不是单一均值。
    # 原因：单条 6000 字样本里，稀有词（升华句之类）的计数方差很大，
    # 拿它跟均值比会得出"灵境原文也偏离基准 322%"这种假结论。
    base = {}
    for k, v in allm.items():
        sv = sorted(v)
        base[k] = [round(sv[int(len(sv) * 0.10)], 2),
                   round(statistics.median(sv), 2),
                   round(sv[int(len(sv) * 0.90)], 2)]
    os.makedirs(os.path.dirname(BASE_CACHE), exist_ok=True)
    json.dump(base, open(BASE_CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--baseline', action='store_true', help='打印基准线原始值')
    a = ap.parse_args()

    print('正在用卖报原著（灵境行者 / 大奉打更人）算基准线……')
    base = build_baseline()
    print('  基准线就绪\n')

    if os.path.isdir(a.path):
        files = [os.path.join(a.path, f) for f in sorted(os.listdir(a.path)) if f.endswith('.md')]
    else:
        files = [a.path]

    keys = list(base.keys())
    # 关键：**必须先把所有样本合并成一个长文本再测**。
    # 用字丰富度、句长/段长波动这些指标都随文本长度变化：
    # 模型输出每段只有几百字，拿它跟 6000 字的基准块直接比，
    # 会得出"用字丰富度 52 vs 20（高 2.7 倍）"这种纯粹由长度造成的假结论。
    texts = [read(f) for f in files]
    combined = ''.join(texts)
    m = metrics(combined)

    print(f'===== 与卖报原著的风格距离 =====')
    print(f'样本 {len(files)} 个，合并后 {len(combined)} 字'
          + (f'（用字丰富度按基准块长度 {BASE_CHUNK} 字截取后测）' if len(combined) > BASE_CHUNK else ''))
    print(f'{"指标":<18}{"卖报 P10":>9}{"P50":>8}{"P90":>8}{"本文":>9}{"判定":>10}')
    out_of_range = 0
    # 长度敏感指标（用字丰富度）必须裁到与基准块同样的长度再测。
    # 实测过两次假象：样本几百字时报"用字丰富度 52 偏高"，样本 9928 字时报"14.7 偏低"，
    # 两次都是长度造成的，不是模型的问题。
    trimmed = combined[:BASE_CHUNK] if len(combined) > BASE_CHUNK else combined
    m_trim = metrics(trimmed)
    for k in keys:
        lo, mid, hi = base[k]
        v = round((m_trim[k] if k == '用字丰富度%' else m[k]), 2)
        if v < lo:
            verdict = '偏低'
            out_of_range += 1
        elif v > hi:
            verdict = '偏高'
            out_of_range += 1
        else:
            verdict = '在区间内'
        print(f'{k:<18}{lo:>9}{mid:>8}{hi:>8}{v:>9}{verdict:>10}')
    print()
    if len(combined) < 4000:
        print('⚠️ 合并后字数偏少（<4000），长度敏感指标（用字丰富度/句长波动/段长波动）不可靠，'
              '请多给几段。')
    print(f'落在卖报 P10~P90 区间之外的指标：{out_of_range} / {len(keys)}')
    print('（区间内 = 与卖报原著在这个轴上看不出差别；落在区间外才值得关注）')
    print()
    print('注：单条短样本（几千字）在稀有词指标上方差很大，'
          '所以这里按多条取均值、并用分位数区间判定，避免误报。')
    if a.baseline:
        print('基准线原始值:', json.dumps(base, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
