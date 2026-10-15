# -*- coding: utf-8 -*-
"""多要点样本（multi-beat）—— 专治「大纲里的爽点写不全」

为什么需要（v8 已实证有效）：
  v6 的十探针里，模型拿到"掀桌 → 示例设定狂亮 → 示例设定横扫 → 瞬杀三名干部 → 一棘贯穿右臂 →
  堂主下跪求饶"这样一份大纲，平均只写出 **2.2/6** 个要点。
  加进多要点样本后（v8），平均覆盖升到 **3.8/6（+73%）**，且出现过一次 6/6 全中。
  根因是原来的训练样本**全是"一个要点 → 一段正文"**，
  模型从没见过"一份要点清单 → 连续多段正文"。

做法（纯重组，不读原文、不新增内容）：把已有样本里同章**相邻的两段或三段**配成一组：
    输入 = 2~3 条情节要点（原来是各段样本的骨架）
    输出 = 2~3 段连续的正文（原来是各段样本的正文）

关于加权（--dup）：
  这类样本占比很小（2.7%），而它是本次唯一被证实有效的改动方向。
  用 `--dup 2` 让同一批样本在一轮里出现两次，把有效占比提到约 8%。
  选择重复而不是照搬其他样本，是因为它教的是**行为模式**（把要点写全），
  不是要记的事实，重复带来的过拟合风险很低。

用法：python scripts/build_multibeat.py [--dup 2]
输出：data_dual/dataset_multibeat.jsonl
"""
import json, os, re, sys, collections

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
DS = r'<项目目录>\Datasets'
SRC = os.path.join(DS, 'data_dual', 'dataset_outline_norm.jsonl')
OUT = os.path.join(DS, 'data_dual', 'dataset_multibeat.jsonl')
GLOSS = os.path.join(DS, 'data_dual', 'glossary.json')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from outline_expand import SYS_RULES, voice_line          # noqa: E402  与推理端同源


def normalize_dash(t):
    def rep(m):
        nxt = t[m.end():m.end() + 1]
        return '……' if (nxt == '' or nxt in '”"」』\n。！？，；') else '：'
    return re.sub(r'——|—|--', rep, t)


def cap_at_sentence(t, cap):
    """按**句末**截断，避免从句子中间切开。"""
    if len(t) <= cap:
        return t
    cut = t[:cap]
    for mark in ('。”', '！”', '？”', '。', '！', '？', '”'):
        i = cut.rfind(mark)
        if i > cap * 0.5:
            return cut[:i + len(mark)]
    return cut


def build(n_beats, groups, gloss, per_beat=450):
    """per_beat: 每幕正文字数上限。
    幕数多时必须调小 —— cutoff 2048 token 是**输入+输出**的总预算，
    而 SYS_RULES(796字)+硬约束(约1500字) 就占掉约 1700 token，留给正文的不到 350 token。
    所以「6 幕 × 450 字」这类样本根本装不下（实测 86/198 条超 cutoff）。
    宁可每幕写短，也要保证**整条样本完整不被截断**（截断＝砍掉最后要点＝教模型漏要点）。"""
    out = []
    for cn, start, rows in groups:
        skels, texts = [], []
        for r in rows:
            sk = re.split(r'请据此|要求：', r['input'])[0].strip()
            skels.append(sk[:150])
            # 每个要点限 450 字（句末收口）。
            # 关键：**绝不能靠 cutoff 去截断多要点样本** —— 被砍掉的正好是最后一个要点，
            # 那等于在教模型"漏掉要点"，与本题目标完全相反。
            # 所以宁可每个要点写短一点，也要保证整条样本完整落在上下文里。
            texts.append(cap_at_sentence(r['output'].strip(), per_beat))
        # 与推理端 build_prompt 的措辞对齐（「章级大纲：」单一文本块，而不是编号清单）。
        # 用户的章级大纲本身就是一段密集的多爽点描述，编号清单跟它对不上形态。
        body = (f'==== 本次要写 ====\n'
                f'《灵境行者》第{cn}章（本次只写这一幕的第 1/1 段，不要写完整章）\n'
                f'章级大纲：' + '；'.join(skels) + '\n'
                f'本章爽点闭环：（见章级大纲）\n\n'
                f'==== 后文走向（仅供对齐，严禁提前写出）====\n'
                f'（本段之后的情节不在本题范围内，请只把上面的要点写完整）\n\n'
                f'==== 硬约束（人物/设定/伏笔）====\n'
                f'【设定】按原著设定书写，不得改写角色的能力来源、位置与形态。\n'
                + (f'【人物声线】{voice_line("".join(texts))}\n' if voice_line("".join(texts)) else '')
                + '\n'
                f'请写出这一幕的正文。')
        body = normalize_dash(body)
        out.append({
            'instruction': SYS_RULES,
            'input': (gloss + '\n\n' + body) if gloss else body,
            'output': normalize_dash('\n\n'.join(texts)),
            'metadata': {'task': 'multibeat', 'book': '灵境行者',
                         'chapter': str(cn), 'beats': str(n_beats)},
        })
    return out


def main():
    dup = 1
    if '--dup' in sys.argv:
        dup = int(sys.argv[sys.argv.index('--dup') + 1])

    rows = [json.loads(l) for l in open(SRC, encoding='utf-8') if l.strip()]
    gloss = ''
    if os.path.isfile(GLOSS):
        names = (json.load(open(GLOSS, encoding='utf-8')).get('灵境行者') or [])
        if names:
            gloss = '【本作专名·只能用这些名字】' + '、'.join(names)

    seg = collections.defaultdict(dict)
    for r in rows:
        m = re.match(r'^SEG-(\d+)-(\d+)$', r['metadata'].get('segment_id') or '')
        if m:
            seg[int(m.group(1))][int(m.group(2))] = r

    # 优先做三段（更能体现"多个要点都要写到"），再补两段
    tri, pair = [], []
    for c in sorted(seg):
        idx = sorted(seg[c])
        for i in idx:
            if i + 1 in seg[c] and i + 2 in seg[c]:
                tri.append((c, i, [seg[c][i], seg[c][i + 1], seg[c][i + 2]]))
        for i in idx:
            if i + 1 in seg[c]:
                pair.append((c, i, [seg[c][i], seg[c][i + 1]]))

    # 4/5/6 幕的窗口 —— 加这些是为了**教模型"连续写更长"**。
    # 原因（2026-09-15 核算）：用户目标是 800~1000 字大纲 → 3000~4000 字正文，
    # 而 cutoff_len 2048 token（≈3380 字）是**输入+输出**的总预算，
    # 大纲 1000 字 + 正文 4000 字 ≈ 3030 token，**单条样本装不下** ✗
    # → 只能靠"训练教连写多幕 + 生成时分幕拼接"。
    # 原来多要点只有 2~3 幕（约 1350 字），模型学到的输出上限就卡在 1350 字；
    # 扩到 4~6 幕（1800~2700 字）后才够得着目标。
    quad = []; quint = []; sext = []
    for c in sorted(seg):
        idx = sorted(seg[c])
        for i in idx:
            if all(i + k in seg[c] for k in range(1, 4)):
                quad.append((c, i, [seg[c][i + k] for k in range(4)]))
            if all(i + k in seg[c] for k in range(1, 5)):
                quint.append((c, i, [seg[c][i + k] for k in range(5)]))
            if all(i + k in seg[c] for k in range(1, 6)):
                sext.append((c, i, [seg[c][i + k] for k in range(6)]))

    a = build(3, tri, gloss)
    b = build(2, pair, gloss)
    q4 = build(4, quad, gloss, per_beat=380)
    q5 = build(5, quint, gloss, per_beat=330)
    q6 = build(6, sext, gloss, per_beat=300)

    # 注意：不要按"输出前 120 字"去重。从同一段开始的三段样本与两段样本，
    # 开头文字是一样的，但**输入不同**（3 个要点 vs 2 个要点），是两个不同的样本。
    # 之前就因为这个 bug 把 51 条三段样本全删了。
    # ⚠️ 过滤必须用**真实 token 数**，不能用字数估。
    # 踩过：我按"1.65 字/token"估出 SAFE=2700 字，结果实测 token/字 ≈ 0.748
    # （硬约束段里数字/符号多，tokenize 更费），4/5/6 幕样本有 86/198 条超出 cutoff。
    # **而多要点样本被 cutoff 截断 = 砍掉最后一个要点 = 教模型漏要点**（本文件开头就写了这条红线）。
    SAFE_TOK = 2000      # cutoff 是 2048，只切真正超标的（设 1900 会把本来合格的也切掉）
    try:
        import os as _os
        _os.environ['HF_HUB_OFFLINE'] = '1'
        from transformers import AutoTokenizer
        _tk = AutoTokenizer.from_pretrained(
            r'<项目目录>\Models\models\Qwen--Qwen2.5-7B-Instruct', trust_remote_code=True)

        def _ntok(r):
            return len(_tk(r['instruction'] + ' ' + r['input'] + r['output'])['input_ids'])
    except Exception as e:
        print(f'[WARN] 分词器不可用（{e}），退回字数估算（cap 2400 字）')

        def _ntok(r):
            return int((len(r['instruction']) + len(r['input']) + len(r['output'])) * 0.85)

    alls = a + b + q4 + q5 + q6
    base = [r for r in alls if _ntok(r) <= SAFE_TOK]
    print(f'  按 token 过滤：{len(alls)} 条 -> {len(base)} 条（门槛 {SAFE_TOK} token）')
    dropped = len(a) + len(b) + len(q4) + len(q5) + len(q6) - len(base)
    print(f'二段 {len(b)} + 三段 {len(a)} + 四段 {len(q4)} + 五段 {len(q5)} + 六段 {len(q6)}'
          f' = {len(a)+len(b)+len(q4)+len(q5)+len(q6)} 条（过滤掉 {dropped} 条超长，保留 {len(base)} 条）')

    final = base * dup
    with open(OUT, 'w', encoding='utf-8') as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    L = [len(r['output']) for r in final]
    print(f'输出 {OUT}')
    print(f'  共 {len(final)} 条（dup={dup}）| 输出 最小{min(L)} 中位{sorted(L)[len(L)//2]} 最大{max(L)} 字')
    print(f'  其中三段 {len([r for r in final if r["metadata"]["beats"]=="3"])} 条，'
          f'两段 {len([r for r in final if r["metadata"]["beats"]=="2"])} 条')
    print('\n----- 示例（三段）-----')
    ex = a[0]
    print(ex['input'][:560])
    print('……【输出开头】……')
    print(ex['output'][:200])


if __name__ == '__main__':
    main()
