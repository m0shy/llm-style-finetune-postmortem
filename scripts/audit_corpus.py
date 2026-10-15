# -*- coding: utf-8 -*-
"""语料体检 —— 把当前语料里每一本书按同一套指标量一遍，输出对照表

用途：判断"书单与权重是否合适"。所有指标**样本量对齐**（每本 30 块 × 6000 字），
否则方差类指标不可比（这条踩过：基准 300 万字 vs 产出 8600 字，方差差 350 倍）。

六项指标各管什么：
  1. AI 指纹词/千字     语言干不干净（越高越像 AI）
  2. 段落长度方差       段落是否 AI 式均匀（越高越像人；文献：AI 32 / 人类 165 / 阈值 80）
  3. 最长连续同构句     句式是否单调（越低越好；卖报 4.3）← 模型当前最像 AI 的一项
  4. 用字丰富度%        词汇是否贫乏（越高越好）
  5. 生活质感/千字      市井日常场景的密度（卖报两本最低 2.5/2.6）
  6. 主角对白占比       群像程度（越低越群像；卖报 50%，玩家凶猛 70%、恐怖屋 74%）
"""
import os, sys, re, glob, random, statistics, collections, argparse

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ai_tells import metrics as ai_metrics, TELL_WORDS   # noqa: E402
from scan_noise import HI, PS_LINE                       # noqa: E402

BOOK = r'<old-lib>'
N, SIZE = 30, 6000

BOOKS = [
    ('灵境行者',       '卖报', 1.0,  [os.path.join(BOOK, '《灵境行者》', '灵境行者*.txt')]),
    ('大奉打更人',     '卖报', 1.0,  [os.path.join(BOOK, '《大奉打更人》', '大奉打更人*.txt')]),
    ('原来我是妖二代', '卖报', 1.0,  [os.path.join(BOOK, '参考', '原来我是妖二代*.txt')]),
    ('我的姐姐是大明星', '卖报', 1.0, [os.path.join(BOOK, '参考', '我的姐姐是大明星*.txt')]),
    ('玩家凶猛',       '辅料', 0.5,  [os.path.join(BOOK, '《玩家凶猛》', '玩家凶猛*.txt')]),
    ('恐怖屋',         '辅料', 0.7,  [os.path.join(BOOK, '参考', '我有一座恐怖屋*.txt')]),
    ('还剩三个月命',   '辅料', 1.0,  [os.path.join(BOOK, '参考', '还剩三个月命*.txt')]),
    ('超神机械师',     '外部', 0.20, [os.path.join(BOOK, '参考', '超神机械师*.txt')]),
    ('这游戏也太真实了', '外部', 0.10, [os.path.join(BOOK, '参考', '这游戏也太真实了*.txt')]),
    ('惊悚乐园',       '外部', 0.10, [os.path.join(BOOK, '参考', '惊悚乐园*.txt')]),
    ('生活系游戏',     '外部', 0.50, [os.path.join(BOOK, '参考', '生活系游戏*.txt')]),
    ('全职高手',       '外部', 0.50, [os.path.join(BOOK, '参考', '全职高手*.txt')]),
    ('我真是大明星',   '外部', 0.40, [os.path.join(BOOK, '参考', '我真是大明星*.txt')]),
]

LIFE = ['饭', '汤', '菜', '碗', '筷', '锅', '面', '粥', '茶', '酒', '超市', '公交', '地铁',
        '校服', '作业', '教室', '钥匙', '台灯', '被单', '枕头', '外套', '小票', '快递',
        '电梯', '楼道', '阳台', '水龙头', '沙发']
QUOTE = re.compile(r'[“"]([^”"]{1,300})[”"]')


def read_glob(ps):
    """走统一稳健读取。"""
    from scan_noise import read_text
    out = []
    for p in ps:
        for f in sorted(glob.glob(p)):
            try:
                out.append(read_text(f))
            except Exception as e:
                # ⚠️ 静默跳过会让体检数字失真（早上那个"用字丰富度 0.8%"就是这么来的）
                print(f'  [警告] 读不到 {os.path.basename(f)}：{type(e).__name__}: {e}')
    return ''.join(out)


def clean(t):
    """与 CPT 语料构建同口径的净化（去章标题行 + HI 污染行）"""
    keep = []
    for line in t.split('\n'):
        s = line.strip()
        if not s:
            continue
        if len(s) <= 24 and s.startswith('第') and ('章' in s or '节' in s):
            continue
        if (len(s) <= 140 and HI.search(s)) or PS_LINE.search(s):
            continue
        keep.append(s)
    return '\n'.join(keep)


def longest_run(sents, k=3):
    runs, cur, prev = [], 1, None
    for s in sents:
        h = s.strip()[:k]
        if not h:
            prev, cur = None, 1; continue
        if h == prev:
            cur += 1
        else:
            if prev is not None:
                runs.append(cur)
            prev, cur = h, 1
    if prev is not None:
        runs.append(cur)
    return max(runs) if runs else 0


def measure(t, seed=7):
    rnd = random.Random(seed)
    if len(t) < SIZE * 3:
        blocks = [t]
    else:
        idx = sorted(rnd.sample(range(0, len(t) - SIZE), min(N, len(t) // SIZE - 1)))
        blocks = [t[i:i + SIZE] for i in idx]
    vals = collections.defaultdict(list)
    for b in blocks:
        n = max(len(b), 1)
        m = ai_metrics(b)
        sents = [s for s in re.split(r'[。！？…]+', b) if s.strip()]
        chars = set()
        for ch in b:
            if '\u4e00' <= ch <= '\u9fff':
                chars.add(ch)
        vals['指纹词'].append(sum(b.count(w) for w in TELL_WORDS) / n * 1000)
        vals['段方差'].append(m['段落长度方差'])
        vals['连续同构'].append(longest_run(sents))
        vals['用字丰富'].append(len(chars) / n * 100)
        vals['生活质感'].append(sum(b.count(w) for w in LIFE) / n * 1000)
        # 主角对白占比（jieba 识别人名）
        try:
            import jieba.posseg as ps, collections as C
            c = C.Counter()
            for w, f in ps.cut(b):
                if f == 'nr' and len(w) >= 2:
                    c[w] += 1
            if c:
                prot = c.most_common(1)[0][0]
                own = tot = 0
                for m2 in QUOTE.finditer(b):
                    bf = b[max(0, m2.start() - 30):m2.start()]
                    cd = [(bf.rfind(pp) + len(pp), pp) for pp in c if c[pp] >= 3 and pp in bf]
                    if cd:
                        tot += 1
                        if max(cd)[1] == prot:
                            own += 1
                vals['主角对白'].append(own / tot * 100 if tot >= 3 else None)
        except Exception as e:
            globals().setdefault('_QFAIL', [])
            _QFAIL.append(f'{type(e).__name__}: {e}')
            vals['主角对白'].append(None)
    if globals().get('_QFAIL'):
        print(f'  [警告] 主角对白测量有 {len(globals()["_QFAIL"])} 块失败（该指标将偏低/缺失）：{globals()["_QFAIL"][0]}')
    return {k: (statistics.mean([x for x in v if x is not None]) if any(x is not None for x in v) else None)
            for k, v in vals.items()}


def main():
    print('===== 语料体检（每本 30 块 × 6000 字，样本量对齐）=====\n')
    print(f'{"书":<18}{"角色":<6}{"权重":<6}{"字数":>10}{"指纹词":>8}{"段方差":>8}{"连续同构":>9}{"用字丰富":>9}{"生活质感":>9}{"主角对白":>9}')
    print('-' * 100)
    res = []
    for name, role, w, ps in BOOKS:
        t = clean(read_glob(ps))
        if not t:
            print(f'{name:<18}{role:<6}{w:<6}  读不到'); continue
        m = measure(t)
        res.append((name, role, w, len(t), m))
        f = lambda k, fmt='{:>8.1f}': (fmt.format(m[k]) if m.get(k) is not None else '   —')
        print(f'{name:<18}{role:<6}{w:<6}{len(t):>10,}{f("指纹词")}{f("段方差", "{:>8.0f}")}'
              f'{f("连续同构", "{:>9.1f}")}{f("用字丰富")}{f("生活质感")}{f("主角对白", "{:>9.1f}")}')
    print('-' * 100)
    # 汇总：按权重算有效占比
    tot_eff = sum(w * ln for _, _, w, ln, _ in res)
    print(f'\n总有效字数（权重×字数）: {tot_eff:,.0f} 字，约 {tot_eff*3/1e6:.1f} MB')
    for role in ['卖报', '辅料', '外部']:
        e = sum(w * ln for n, r, w, ln, _ in res if r == role)
        print(f'  {role}: {e/tot_eff*100:>5.1f}%（{e:,.0f} 字）')
    # 加权后的指标期望值（粗估：按权重加权）
    print('\n按权重加权的指标期望（反映模型实际"看到"的分布）:')
    for k in ['指纹词', '段方差', '连续同构', '用字丰富', '生活质感', '主角对白']:
        num = den = 0
        for _, _, w, ln, m in res:
            v = m.get(k)
            if v is None: continue
            num += v * w * ln; den += w * ln
        if den: print(f'  {k:<8}{num/den:>8.1f}')


if __name__ == '__main__':
    main()
