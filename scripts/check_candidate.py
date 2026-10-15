# -*- coding: utf-8 -*-
"""候选书体检 —— 用数据决定"这本书能不能进 CPT 语料"

为什么需要：选语料时最容易犯的错是**看作者名气**。但"白金/大神"是商业头衔，
不等于"语言干净"—— 而且当下不少成熟作者已在用 AI 辅助写作，他们书里可能自带 AI 味，
加进语料正好污染要压掉的东西。

所以把选择变成可量化的三件事：
  1. **AI 味体检**（六项，与卖报原著基准对比）——书本身干不干净
  2. **与卖报的接近度**（关键风格轴的距离）——加进去会不会把"像卖报"稀释掉
  3. **体量与维度**（字数 / 对白占比 / 情感词密度）——补的是不是我们缺的那一块

用法：
  python scripts/check_candidate.py "D:\\path\\候选书.txt"
  python scripts/check_candidate.py "D:\\path\\候选书.txt" --name "玩家凶猛"
"""
import os, sys, glob, random, statistics, argparse

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ai_tells import metrics, read_any          # noqa: E402
from style_gap import metrics as style_metrics  # noqa: E402

BOOK = r'<old-lib>'
MAIBAO = [
    os.path.join(BOOK, '《灵境行者》', '灵境行者(1-500章).txt'),
    os.path.join(BOOK, '《灵境行者》', '灵境行者(501-1000章).txt'),
    os.path.join(BOOK, '《大奉打更人》', '大奉打更人(1-500章).txt'),
    os.path.join(BOOK, '《大奉打更人》', '大奉打更人(501-955章).txt'),
]
# 风格轴里"越像卖报越好"的方向：绝对值距离，越小越像
AXES = ['对白占比%', '平均句长', '句长波动(标准差)', '平均段长', '段长波动(标准差)']


def chunked_metrics(text, size=6000, n=30, seed=0):
    if len(text) < size * 3:
        return metrics(text), style_metrics(text)
    rnd = random.Random(seed)
    idx = sorted(rnd.sample(range(0, len(text) - size), min(n, max(1, len(text) // size - 1))))
    ms = [metrics(text[i:i + size]) for i in idx]
    ss = [style_metrics(text[i:i + size]) for i in idx]
    return ({k: statistics.mean(m[k] for m in ms) for k in ms[0]},
            {k: statistics.mean(s[k] for s in ss) for k in ss[0]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--name', default=None)
    ap.add_argument('--size', type=int, default=6000)
    ap.add_argument('--n', type=int, default=30)
    a = ap.parse_args()

    name = a.name or os.path.basename(a.path)
    base_txt = ''.join(read_any(p) for p in MAIBAO if os.path.isfile(p))
    if not base_txt:
        print('找不到卖报原著，无法建基准。')
        return
    bm, bs = chunked_metrics(base_txt, a.size, a.n, seed=1)

    txt = read_any(a.path)
    if not txt:
        print(f'读不到内容：{a.path}')
        return
    cm, cs = chunked_metrics(txt, a.size, a.n, seed=2)

    print(f'===== 候选书体检：{name} =====')
    print(f'字数 {len(txt):,} | 与卖报原著（{len(base_txt):,} 字）分块对比，每块 {a.size} 字\n')

    # ⚠️ 阈值必须**以卖报本人为基准做相对判断**，不能用文献的绝对阈值。
    # 踩过的坑：文献说"AI 指纹词 ≤5/千字"（那是基于 AI 均值 12.3 定的），
    # 但卖报本人只有 1.3、模型产出是 3.3 —— 绝对值都没超，相对却翻了一倍多。
    # 用绝对阈值会把模型的产出判成"干净"，工具直接失效（反例验证抓到的）。
    print('【一】AI 味六项 —— 这本书本身干不干净（阈值＝卖报本人的倍数）')
    checks = [
        ('AI指纹词 每千字', '低', 1.5, 2.5),
        ('情绪词 每千字', '低', 2.0, 4.0),
        ('段落长度方差', '绝对高', 150.0, 80.0),   # AI 32 / 人类 165 / 阈值 80（文献口径）
        ('最长连续同构句', '低', 1.0, 1.3),    # 低者好：warn > +1, fail > ×1.3
    ]
    bad = warn = 0
    for k, direction, w, f in checks:
        v, b = cm.get(k, 0), bm.get(k, 0)
        if direction == '低':
            lvl = 'fail' if v > b * f else ('warn' if v > b * w else 'ok')
            show = f'卖报×{f:.1f}={b*f:.1f} / ×{w:.1f}={b*w:.1f}'
        elif direction == '绝对高':
            # 判的是"段落是否过于均匀"（AI 特征），与卖报像不像无关 → 用文献绝对阈值
            lvl = 'fail' if v < f else ('warn' if v < w else 'ok')
            show = f'AI 32 / 人类 165 / 阈值 {f:.0f}'
        else:
            lvl = 'fail' if v < b * f else ('warn' if v < b * w else 'ok')
            show = f'卖报×{f:.1f}={b*f:.1f} / ×{w:.1f}={b*w:.1f}'
        bad += (lvl == 'fail'); warn += (lvl == 'warn')
        print(f'  {k:<18} 卖报 {b:>7.1f} | 候选 {v:>7.1f} | 界限 {show:<26} '
              f'{"✅" if lvl=="ok" else ("⚠️" if lvl=="warn" else "❌")}')

    print('\n【二】与卖报的接近度（关键风格轴，差越小越像）')
    dist = 0.0
    for k in AXES:
        v, b = cs.get(k, 0), bs.get(k, 0)
        d = abs(v - b)
        rel = d / max(abs(b), 1e-6) * 100
        dist += rel
        print(f'  {k:<18} 卖报 {b:>8.1f} | 候选 {v:>8.1f} | 偏离 {rel:>5.1f}%')
    print(f'  → 综合偏离 {dist/len(AXES):.1f}%（越小越像卖报）')

    print('\n【三】体量与维度')
    print(f'  字数          {len(txt):,} 字  ≈ {len(txt)/1e4:.0f} 万字（对 43.7MB 语料而言 +{len(txt)/43.7e6*100:.1f}%）')
    print(f'  对白占比      候选 {cs.get("对白占比%",0):.1f}%  vs 卖报 {bs.get("对白占比%",0):.1f}%')

    # ---- 维度画像：语料现在缺哪一块，这本能不能补 ----
    # 依据（2026-09-15 实测五本）：**最大缺口是群像对白** ——
    # 五本里四本只有 1~5 个具名说话人（灵境 13 个），所以模型一直只会写主角一个人说话。
    # 其次是生活质感（卖报两本最低）、情感动作（仅剩三个月命高，而它只占语料 1.2%）。
    LIFE = ['饭', '汤', '菜', '碗', '筷', '锅', '面', '粥', '茶', '酒', '超市', '公交', '地铁',
            '校服', '作业', '教室', '钥匙', '台灯', '被单', '枕头', '外套', '小票', '快递',
            '电梯', '楼道', '阳台', '水龙头', '沙发']
    INTI = ['抱住', '攥住', '握住', '拍了拍', '摸了摸', '揉了揉', '拉了拉', '肩上', '手心',
            '额头', '眼泪', '低头', '别过脸', '背对', '并肩', '搀']
    # ⚠️ 取样必须**覆盖全书**，不能只取开头。
    # 踩过：只取前 150 万字时，"情感动作"在五本上都只有 0.3~0.4，
    # 而全书实测是 1.2~2.8 —— 因为感情戏多在中后段，只取开头会把这一项系统性低估。
    import random as _r
    _rnd = _r.Random(11)
    if len(txt) > 1_800_000:
        _idx = sorted(_rnd.sample(range(0, len(txt) - 200_000),
                                  min(8, max(1, len(txt) // 200_000))))
        t2 = ''.join(txt[i:i + 200_000] for i in _idx)
    else:
        t2 = txt
    n2 = max(len(t2), 1)
    life = sum(t2.count(w) for w in LIFE) / n2 * 1000
    inti = sum(t2.count(w) for w in INTI) / n2 * 1000
    # 具名说话人数（群像度）—— 用 voice_check 的归属逻辑
    # 群像度＝**主角对白占比**（越低越群像）。用 jieba 词性标注识别人名。
    # ⚠️ 这一步换过三次实现，前两次都是错的：
    #   ① 依赖人手列的人名表（那份表围绕灵境建）→ 数恐怖屋得 0 个、玩家凶猛得 2 个，全是假数据
    #   ② 朴素"X道"正则 + 停用词 → 灵境数出 756 个（"忍不住说""低声道"全当人名）
    #   ③ jieba 的 nr 词性 + 频次阈值 + 用"主核对白占比"当指标 ← 现在这个，与人工核对一致
    # 真实基准：卖报两本都是 **50.3%**（一半台词归别人）＝群像；
    #          玩家凶猛 69.8% / 恐怖屋 74.3% ＝单主角为主。
    prot_share = None
    try:
        import jieba.posseg as _ps, collections as _C2, re as _re2
        _c2 = _C2.Counter()
        for w_, f_ in _ps.cut(t2[:400000]):
            if f_ == 'nr' and len(w_) >= 2:
                _c2[w_] += 1
        if _c2:
            _prot = _c2.most_common(1)[0][0]
            _names = [k for k, v in _c2.items() if v >= 20]
            _own = _C2.Counter()
            for _m in _re2.finditer(r'[\u201c"]([^\u201d"]{1,300})[\u201d"]', t2):
                _bf = t2[max(0, _m.start() - 30):_m.start()]
                _cd = [(_bf.rfind(n_) + len(n_), n_) for n_ in _names if n_ in _bf]
                if _cd:
                    _own[max(_cd)[1]] += 1
            _tot = sum(_own.values()) or 1
            prot_share = _own.get(_prot, 0) / _tot * 100
    except Exception:
        pass
    # 现语料的参照值（实测）
    # 参照值＝五本实测（全书随机取样口径，与这里一致）
    REF = {'生活质感': (2.4, 4.4)}
    print('\n【四】维度画像 —— 这本补的是哪一块（现语料的最大缺口是**群像对白**）')
    print(f'  生活质感  {life:>6.1f}/千字   现语料区间 {REF["生活质感"][0]}~{REF["生活质感"][1]}'
          f'   {"✅ 能补" if life >= REF["生活质感"][1] else ""}')
    # 「情感动作」这一项先不展示 —— 前后两次用的词表不一致（一次含 笑/靠/哭，一次不含），
    # 导致同一本书量出 2.8 和 0.4 两个值。**没校准好就不展示**，免得又用一个错指标做决定。
    print(f'  情感动作  {inti:>6.1f}/千字   （这一项词表尚未校准，仅作参考，不作判据）')
    if prot_share is None:
        print('  主角对白占比  （jieba 不可用，跳过）')
    else:
        # 基准值取**本工具口径下灵境的实测值 62%**。
        # （另有全量前 120 万字的测法得到 50.3% —— 取样范围不同数值会差约 10 个百分点，
        #  所以基准必须和检测用同一口径，不能拿另一个口径的数字来比。）
        print(f'  主角对白占比 {prot_share:>6.1f}%  灵境基准 **62%**（越低越群像）'
              f'   {"✅ 群像好" if prot_share <= 64 else ("⚠️ 偏单主角" if prot_share <= 70 else "❌ 单主角为主")}')

    print('\n【结论建议】')
    if bad >= 1:
        print('  ❌ **不建议进语料**：有 %d 项越过了"卖报的 2.5 倍/0.55 倍"这条线。' % bad)
        print('     —— 加了会把要压掉的 AI 味带回来，与目标相反。')
    elif warn >= 2 or dist / len(AXES) > 40:
        print('  ⚠️ **谨慎**：AI 味有 %d 项偏警戒（或与卖报笔法偏离 %.0f%%）。'
              % (warn, dist / len(AXES)))
        print('     若加，比例压小（不超过语料的 15%），否则会稀释"像卖报"。')
    elif dist / len(AXES) > 20:
        print('  ⚠️ **谨慎**：语言本身干净，但与卖报的笔法偏离较大（%.0f%%）。'
              '\n     若加，比例要压小（建议不超过语料的 15%%），否则会稀释"像卖报"。' % (dist / len(AXES)))
    else:
        print('  ✅ **可以进语料**：AI 味干净、与卖报笔法接近。')
        print('     建议比例：作为"补维度"的辅料，合计不超过卖报两本的份额。')
    print('\n注：这三项覆盖"可量化"的部分。**仍要人工抽读两三章** —— '
          '逻辑 bug（人设/时空矛盾）与"华美空洞"这两条测不出来，而编辑判 AI 稿主要看这两条。')


if __name__ == '__main__':
    main()
