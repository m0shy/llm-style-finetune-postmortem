# -*- coding: utf-8 -*-
"""声线区分度检测 —— 量「每个人的语气是否真的不一样」

为什么需要：
  用户明确要求「**能分辨出每一个人的语气都应该是怎么样的**」。
  但此前这一条既没训练过（样本的硬约束段只有人名、没有语气），
  也没有任何检测手段 —— 只能靠"读起来感觉像不像"，等于没法验收。

做法：
  1. 从生成稿里抽对白，并把每句对白归到说话人
     （中文小说的归属惯例：`张三道：“……”`、`“……”，张三说`、`张三冷笑：“……”`）
  2. 对每个说话人算一组声线特征：对白长度、短句占比、句末语气词、问句率、感叹率、口头禅命中
  3. 判定标准：**人跟人之间的差异，要明显大于同一个人自己前后的波动**
     （组间方差 / 组内方差，比值越大越"人人有别"；接近 1 就是"千人一面"）

用法：
  python scripts/voice_check.py 稿件.md
  python scripts/voice_check.py 章节目录/
  python scripts/voice_check.py 稿件.md --min-lines 3     # 至少这么多句对白才算一个"有声线的角色"
"""
import os, re, sys, json, statistics, collections, argparse

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

VAULT = r'<项目目录>\《自创作品》'
CARD_DIRS = ('02_人物',)
# 源书人物（用来检源书稿，或生成稿里混进来的串台角色）
SRC_NAMES = ['张元清', '关雅', '傅青阳', '夏侯傲天', '赵城隍', '寇北月', '外婆', '江玉饵',
             '孙淼淼', '灵钧', '陈薇', '止杀宫主', '三道山娘娘', '银瑶郡主', '李东泽',
             '怀庆', '宋卿', '王泰', '许七安', '李妙真', '褚采薇']

TAIL_PARTICLES = '啊吧吗呢嗯哈嘛哦啦咧嘿唉咯呀哇哦'
QUOTE = re.compile(r'[“"]([^”"]{1,120})[”"]')
# 「某人 + 说话动词」
SPEAK = r'(?:道|说|问|答|喊|叫|笑|冷笑|哼|怒|吼|嘀咕|嘟囔|开口|沉声|笑道|说道|低声道|冷笑道)'
NAME_BEFORE = re.compile(r'([\u4e00-\u9fff]{2,4})' + SPEAK + r'[，,：:]?\s*$')
NAME_AFTER = re.compile(r'^\s*[，,。！？…]*\s*([\u4e00-\u9fff]{2,4})' + SPEAK)


def read(p):
    for enc in ('utf-8', 'gbk'):
        try:
            return __import__('scan_noise').read_text(p)   # 2026-09-16 统一修缮：原 errors='ignore' 对 GBK 静默出错
        except Exception:
            continue
    return ''


def load_names():
    names = set(SRC_NAMES)
    for sub in CARD_DIRS:
        d = os.path.join(VAULT, sub)
        if os.path.isdir(d):
            names |= {f[:-3] for f in os.listdir(d) if f.endswith('.md')}
    names |= {'主角', '示例角色1', '示例角色2', '示例角色7', '示例角色6', '示例角色14', '示例角色12',
              '示例角色8', '示例角色11', '示例角色10', '示例角色3', '老赵', '老方'}
    return sorted((n for n in names if 2 <= len(n) <= 4), key=len, reverse=True)


def dialogue_by_speaker(text, names):
    """抽出 (说话人, 对白内容)。归属不明的不计入。

    归属策略：**取引号前最近出现的角色名**（往前看 30 字）。
    为什么不用「人名+说话动词紧贴」的正则：中文小说的实际写法经常是
        「主角冷笑一声，眼神阴森森的：
          "我不认识你们！"」
    人名和引号之间隔了十几个字，紧贴式正则会把绝大多数对白漏掉
    （实测只认出 4 句，改成"最近人名"后能认出几十句）。
    """
    out = []
    for m in QUOTE.finditer(text):
        line = m.group(1)
        before = text[max(0, m.start() - 30):m.start()]
        after = text[m.end():m.end() + 30]
        who = None
        # 引号前最近的角色名（越靠后越可能是说话人）
        cand = [(before.rfind(n) + len(n), n) for n in names if n in before]
        if cand:
            who = max(cand)[1]
        else:
            cand2 = [(len(after) - after.find(n), n) for n in names if n in after]
            if cand2:
                who = min(cand2)[1]
        if who:
            out.append((who, line))
    return out


def _strip_tail(x):
    return x.rstrip('。！？…，,、；;：:”"~～ 	')


def features(lines):
    """一个说话人的声线特征向量。"""
    n = len(lines)
    lens = [len(x) for x in lines]
    joined = ''.join(lines)
    return {
        '对白数': n,
        '平均长度': round(statistics.mean(lens), 1),
        '长度波动': round(statistics.pstdev(lens), 1) if n > 1 else 0.0,
        '短句率%': round(sum(1 for x in lens if x <= 6) / n * 100, 1),
        # 先剥掉句末标点再判，否则 "……啊？" 这种会被算成"不是语气词尾"，
        # 实测会让这一项恒为 0（原著和模型稿都是 0.0，一眼就知道是 bug）。
        '语气词尾%': round(sum(1 for x in lines if _strip_tail(x) and _strip_tail(x)[-1] in TAIL_PARTICLES) / n * 100, 1),
        '问句率%': round(sum(1 for x in lines if x.rstrip().endswith(('？', '?'))) / n * 100, 1),
        '感叹率%': round(sum(1 for x in lines if x.rstrip().endswith(('！', '!'))) / n * 100, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--min-lines', type=int, default=3)
    a = ap.parse_args()

    names = load_names()
    files = ([os.path.join(a.path, f) for f in sorted(os.listdir(a.path)) if f.endswith('.md')]
             if os.path.isdir(a.path) else [a.path])

    all_dlg = []
    for f in files:
        all_dlg += dialogue_by_speaker(read(f), names)

    by = collections.defaultdict(list)
    for who, line in all_dlg:
        by[who].append(line)
    by = {k: v for k, v in by.items() if len(v) >= a.min_lines}

    if not by:
        print(f'没抽到足够的对白（要求每个角色至少 {a.min_lines} 句）。')
        print('可能原因：稿子对白少、或说话人多但每人都只有一两句。')
        return

    print(f'===== 声线区分度（共 {len(all_dlg)} 句对白，{len(by)} 个角色达门槛）=====\n')
    keys = ['平均长度', '短句率%', '语气词尾%', '问句率%', '感叹率%']
    print(f'{"角色":<8}{"对白数":>6}' + ''.join(f'{k:>11}' for k in keys))
    table = {}
    for who, lines in sorted(by.items(), key=lambda x: -len(x[1])):
        fe = features(lines)
        table[who] = fe
        print(f'{who:<8}{fe["对白数"]:>6}' + ''.join(f'{fe[k]:>11}' for k in keys))

    # 组间方差 / 组内方差：>1 说明"人跟人不一样"，接近 1 就是"千人一面"
    print('\n----- 区分度判定 -----')
    scores = []
    for k in keys:
        cols = [table[w][k] for w in table]
        if len(cols) < 2:
            continue
        mu = statistics.mean(cols)
        between = statistics.pvariance(cols)
        # 组内：每个角色自己的波动（用长度波动近似）
        within = statistics.mean([max(table[w]['长度波动'], 0.5) for w in table])
        ratio = between / (within + 1e-6)
        scores.append(ratio)
        verdict = '✅ 区分明显' if ratio >= 2 else ('⚠️ 有点区分' if ratio >= 1 else '❌ 区分不足')
        print(f'  {k:<10} 组间方差 {between:7.1f} / 组内波动 {within:5.1f} = {ratio:5.2f}  {verdict}')
    if scores:
        avg = statistics.mean(scores)
        print(f'\n综合区分度：{avg:.2f}  '
              + ('✅ 人人有别' if avg >= 2 else '⚠️ 部分角色分得开' if avg >= 1 else '❌ 千人一面'))
    print('\n注：组间/组内比值 ≥ 2 视为"听得出来是谁在说话"；≥ 1 是"有一点区分"；< 1 是"千人一面"。')
    print('这条只测**可量化**的层面（长短、语气词、句式），测不出"这个人在不在乎"这类语义层的东西。')


if __name__ == '__main__':
    main()
