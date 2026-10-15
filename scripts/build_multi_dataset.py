# -*- coding: utf-8 -*-
"""五书合成数据集构建器（续写式 + 大纲式）

书单与定位（卖报文风为锚）：
  灵境行者     卖报小郎君  都市暗线游戏      —— 主锚（题材与笔法双吻合）
  大奉打更人   卖报小郎君  古代悬疑探案      —— 副锚（节奏、群像、对白）
  玩家凶猛     黑灯夏火    都市异能/自创作品 —— 最贴近本作题材，学副本设计
  恐怖屋       空调        灵异恐怖          —— 学氛围压迫感与悬念铺陈
  还剩三个月命 汐尺        末日丧尸/情感     —— 学短促节奏与情感张力

配额原则：锚书配额最高，其余按"取长补短"递减；并保留少量通用回放数据防能力退化。

用法：
  python scripts/build_multi_dataset.py --out data_dual/dataset_multi.jsonl
"""
import json, os, re, sys, io, random, hashlib, argparse
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from outline_expand import voice_line      # noqa: E402  与推理端同源


try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass
BOOK_HOME = r'<old-lib>'
DS = r'<项目目录>\Datasets'

BOOKS = {
    '灵境行者': ('锚·都市暗线', [
        os.path.join(BOOK_HOME, '《灵境行者》', '灵境行者(1-500章).txt'),
        os.path.join(BOOK_HOME, '《灵境行者》', '灵境行者(501-1000章).txt'),
        os.path.join(BOOK_HOME, '《灵境行者》', '灵境行者(1001-1050章).txt')]),
    '大奉打更人': ('锚·古代探案', [
        os.path.join(BOOK_HOME, '《大奉打更人》', '大奉打更人(1-500章).txt'),
        os.path.join(BOOK_HOME, '《大奉打更人》', '大奉打更人(501-955章).txt')]),
    # ⚠️ 2026-09-16 新增：卖报本人另外两本完本都市作 —— **同一支笔，零稀释** ✓
    #    《原来我是妖二代》都市异术超能 262万；《我的姐姐是大明星》**都市生活** 212万。
    #    加它们是因为：SFT 是"锁风格"的一层，卖报占比越高越好；
    #    而这两本正好补「现代都市 + 生活日常」—— 用户作品里大量场景就长这样。
    '原来我是妖二代': ('锚·都市异能（卖报本人）', [
        os.path.join(BOOK_HOME, '参考', '原来我是妖二代.txt')]),
    '我的姐姐是大明星': ('锚·都市生活（卖报本人）', [
        os.path.join(BOOK_HOME, '参考', '我的姐姐是大明星.txt')]),
    '玩家凶猛': ('辅·都市异能', [
        os.path.join(BOOK_HOME, '《玩家凶猛》', '玩家凶猛.txt')]),
    '恐怖屋': ('辅·灵异氛围', [
        os.path.join(BOOK_HOME, '参考', '我有一座恐怖屋.txt')]),
    '还剩三个月命': ('辅·感情戏（短篇·密集采样）', [
        os.path.join(BOOK_HOME, '参考', '还剩三个月命，请让我从容赴死.txt')]),
}

# 每本书的滑窗参数：(前文下限, 前文上限, 续写下限, 续写上限)
# 说明：这本短篇是用户特意拿来补「恋爱与殉情」描写的，篇幅只有 16.7 万字（其他书 300~420 万字），
#       按长篇的稀疏窗口只能采到 104 条、占比不到 4%，教不动模型。
#       所以对它改用更密的滑窗，把 3.7% 提到 14% 左右，并允许同书内部小幅重叠。
WIN = {
    '还剩三个月命': (150, 220, 190, 290),
}
WIN_DEFAULT = (320, 520, 380, 560)

GLOSSARY_PATH = os.path.join(DS, 'data_dual', 'glossary.json')
try:
    GLOSSARY = json.load(open(GLOSSARY_PATH, encoding='utf-8'))
except Exception:
    GLOSSARY = {}

# 与推理端完全同格式的专名块。
# 为什么必须加：v5 评测实证，模型在没见过专名块的情况下会无视它，
# 直接拿《灵境行者》的人物（李东泽，该书出现 717 次）来填。训练里带上，
# 模型才学得会"锚点里列的名字就是要用的名字"这套机制。
GLOSS_PREFIX = '【本作专名·只能用这些名字】'


def gloss_block(book):
    names = GLOSSARY.get(book) or []
    return GLOSS_PREFIX + '、'.join(names) if names else ''


CH_PAT = re.compile(r'^\s*第\s*[0-9一二三四五六七八九十百千零两]+\s*[章回节]\s*.*$')

# 作者明令禁用破折号，但源书（卖报原著）大量使用。
# v6 实测：C1/F1/G2 三个探针各冒出 1 处。所以语料侧做一次规范化，
# 让模型不再从源文学到这个习惯（只改标点，不改字词）。
def normalize_dash(t):
    def rep(m):
        nxt = t[m.end():m.end() + 1]
        return '……' if (nxt == '' or nxt in '”"」』\n。！？，；') else '：'
    return re.sub(r'——|—|--', rep, t)
# ⚠️ 2026-09-15 换成与 CPT 语料共用的高精度过滤（HI），旧表漏了作者话。
# 实测：旧 NOTE_PAT 过滤后的 SFT 数据里仍有 19 行 HI 命中（来自源书作者话）。
def _hi():
    import os as _o, sys as _s
    _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from scan_noise import HI, PS_LINE

    # ⚠️ 2026-09-16 修：HI 里的 ps 模式有 {0,80} 长度上限，长作者话会漏（实测漏了 1 行：
    #    "ps：九十八章吧，应该是九十八章，我写错了，把金莲道长写成赵守了。…"）
    #    PS_LINE 是不限长度的 'ps：' 行首检测 —— 与 CPT 语料用同一套。
    class _P:
        @staticmethod
        def search(t):
            return HI.search(t) or PS_LINE.search(t)

        @staticmethod
        def findall(t):
            return HI.findall(t) + PS_LINE.findall(t)

    return _P
NOTE_PAT = _hi()

INSTR_CONT = [
    "接着下面这段文字继续往下写。保持同样的笔法与节奏，写成一段连贯的正文。",
    "以下是一段小说的开头，请顺着写下去。要求：长短句交错、画面感强，与上文无缝衔接。",
    "续写下面这段小说。文风与上文保持一致，注重感官细节与人物动作。",
    "请把下面这一段接着写下去，不要重复上文内容，直接进入后续情节。",
    "以下是小说的一段正文，请续写后面的内容。要求：节奏自然、画面清晰、对话生动。",
    "顺着下面的文字继续写。保持同一叙述视角与语气，写成一段完整的情节。",
]

CTX_MIN, CTX_MAX = 320, 520
OUT_MIN, OUT_MAX = 380, 560


def load_paras(files):
    out, cur_title, cur = [], None, []
    for f in files:
        if not os.path.isfile(f):
            print('  缺文件', f)
            continue
        # ⚠️ 不能写 encoding='utf-8', errors='ignore' —— 对 GBK 文件它永远不会报错，
        # 非法字节被静默丢弃，导致《恐怖屋》等 GBK 书在数据里变乱码。
        # 走统一稳健读取（严格解码 + 中文占比检查）。
        from scan_noise import read_text
        _txt = read_text(f)
        if True:
            for line in _txt.split('\n'):
                s = line.strip()
                if not s:
                    continue
                if CH_PAT.match(s):
                    if cur_title is not None and cur:
                        out.append((cur_title, cur))
                    cur_title, cur = s, []
                elif cur_title is not None:
                    # ⚠️ 2026-09-15 修正：这里必须**按行删掉高精度污染**。
                    # 原来只靠后面的启发式「短段落命中≥2次才丢」—— 而像
                    # "ps：先让许白嫖'不对'个十小时吧。" 只命中 1 次，就漏过去了 ✗。
                    # 实测：旧数据正文里仍有 5~8 行真作者话（ps：求票/感谢盟主打赏/均订数据）。
                    if len(s) <= 140 and NOTE_PAT.search(s):
                        continue
                    cur.append(s)
            if cur_title is not None and cur:
                out.append((cur_title, cur))
    clean = []
    for t, ps in out:
        body = ''.join(ps)
        if len(body) < 400 and len(NOTE_PAT.findall(body)) >= 2:
            continue
        ps = [p for p in ps if not (len(p) < 220 and len(NOTE_PAT.findall(p)) >= 2)]
        if ps:
            clean.append((t, ps))
    return clean


def build_book(name, files, quota, win=None):
    cmin, cmax, omin, omax = win or WIN_DEFAULT
    chs = load_paras(files)
    total = sum(len(''.join(ps)) for _, ps in chs)
    rows, rnd = [], random.Random(20260911)
    seen = set()
    for title, ps in chs:
        text = '\n'.join(ps)
        pos, L = 0, len(text)
        while pos + cmin + omin < L:
            cs = pos
            ce = min(L, cs + rnd.randint(cmin, cmax))
            k = text.rfind('。', cs, ce)
            if k < cs + cmin - 60:
                k = text.rfind('”', cs, ce)
            if k <= cs:
                pos += max(200, cmin // 2)
                continue
            ctx = text[cs:k + 1]
            os_, oe = k + 1, min(L, k + 1 + rnd.randint(omin, omax))
            k2 = text.rfind('。', os_ + omin - 80, oe)
            if k2 <= os_:
                pos = oe
                continue
            out = text[os_:k2 + 1].strip()
            pos = k2 + 1
            if len(ctx) < cmin - 50 or len(out) < omin - 80:
                continue
            if NOTE_PAT.search(out) or NOTE_PAT.search(ctx):
                continue
            key = hashlib.md5(ctx[-80:].encode('utf-8')).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            rows.append({'book': name, 'chapter': title,
                         'ctx': normalize_dash(ctx), 'out': normalize_dash(out)})
    rnd.shuffle(rows)
    got = rows[:quota]
    print(f'{name}: {len(chs)} 章 / {total} 字  窗口{win or WIN_DEFAULT}  -> 候选 {len(rows)}，取 {len(got)}')
    return got


def cap_at_sentence(t, cap):
    """把过长的正文按**句末**截断，避免 tokenizer 从句子中间切。

    为什么需要：cutoff_len 是硬截断。大纲样本的 prompt 约 900 tokens，留给输出的只有
    约 1150 tokens（≈1560 字）。超出就会被拦腰砍掉，模型会学成"写到一半就停"。
    在这里先按句末收口，至少语义是完整的。
    """
    if len(t) <= cap:
        return t
    cut = t[:cap]
    for mark in ('。”', '！”', '？”', '。', '！', '？', '”'):
        i = cut.rfind(mark)
        if i > cap * 0.6:
            return cut[:i + len(mark)]
    return cut


# ---- 情绪浓度过滤（数据侧对抗 AI 腔）----
# 同场景对比实测：卖报写一场戏是"直陈情绪 0.0 / 比喻词 0.0 每千字"，
# 模型写同一场戏是"1.99 / 3.98"。诊断是——**模型在往卖报的稿子里加卖报自己不加的东西**。
# 所以这里把源书里情绪浓度**最高的那一档样本剔掉**，让训练分布向作者本人的克制写法偏移。
_NOISE_TWO = False   # True = 只按「直陈情绪+比喻词」算（v15/v18 口径）


def _speaker_count(text):
    """这段文本里有几个不同的具名说话人。

    为什么要这个：v15 的情绪浓度过滤把「多人对白的感情戏」一起删掉了
    （感情戏天然情绪浓度高，也天然是"妹妹说话、妹妹说话"的场景），
    结果模型只会写主角一个人说话 —— C1 里有对白的角色从 2 个降到 1 个。
    所以剔除时要**跳过多人对白的样本**，保住"每个角色都开口"的样子。
    """
    try:
        from voice_check import dialogue_by_speaker, load_names as _ln
        names = _ln()
    except Exception:
        return 0
    try:
        dlg = dialogue_by_speaker(text, names)
        return len(set(w for w, _ in dlg))
    except Exception:
        return 0


def style_noise(text):
    """每千字里「AI 腔」杂质的密度 = 直陈情绪 + 比喻词 + 套话连接词 + 升华句。

    ⚠️ 词表**从 style_gap 现读**，不在这里另抄一份 ——
    否则"过滤口径"和"检测口径"会漂移，过滤掉的不是检测到的那批东西。
    （v15 时只算「直陈情绪 + 比喻词」，那两项压下去了；
      v18 剩的两项恰好是「升华句 0.8、套话连接词 0.8」，所以这里扩到四项。）

    为什么要滤：模型爱加这些，是因为它没见过足够多"不加照样好看"的写法。
    把源书里杂质浓度最高的那一档样本剔掉，训练分布就往作者本人的克制写法偏移。
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from style_gap import EMO, SIM, FILLER, GRAND
        # 只算两项（v15/v18 的口径）还是四项（v19 起）——
        # 留这个开关是为了**保持单变量对照**：要测指令改动时，过滤器口径不能跟着变。
        words = list(EMO) + list(SIM) if _NOISE_TWO else list(EMO) + list(SIM) + list(FILLER) + list(GRAND)
    except Exception:
        # 兜底：万一 style_gap 读不到（比如缺 baseline 缓存），至少别让构数挂掉
        words = ['心里一暖', '心中一暖', '感到', '意识到', '仿佛', '宛如',
                 '然而', '于是', '不由得', '这一刻', '此刻']
    n = max(len(text), 1)
    hits = sum(text.count(w) for w in words)
    return hits / n * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(DS, 'data_dual', 'dataset_multi.jsonl'))
    ap.add_argument('--quota', default='灵境行者=900,大奉打更人=700,玩家凶猛=700,恐怖屋=450,还剩三个月命=350')
    ap.add_argument('--outline', default=os.path.join(DS, 'data_dual', 'dataset_outline_structured.jsonl'))
    ap.add_argument('--multibeat', default=os.path.join(DS, 'data_dual', 'dataset_multibeat.jsonl'))
    ap.add_argument('--noise-two', action='store_true',
                    help='过滤器只算两项（直陈情绪+比喻词），与 v15/v18 口径一致')
    ap.add_argument('--emo-drop', type=float, default=0.15,
                    help='剔除情绪浓度最高的这一比例的样本（治 AI 腔，默认 0.15）')
    ap.add_argument('--replay', default=r'<项目目录>\LLaMA-Factory\data\general_replay.jsonl')
    # 注意：这个文件一直存在，但旧默认路径写成了 data_dual/general_replay_dual.jsonl（不存在），
    # 加上我又习惯性传 --replay ""，导致 v8/v10/v11c/v12 四轮的通用回放全都是关着的。
    # 长训练必须打开，否则通用能力（说人话）会随训练量上升而退化。
    a = ap.parse_args()
    global _NOISE_TWO
    _NOISE_TWO = a.noise_two

    quotas = dict(kv.split('=') for kv in a.quota.split(','))
    quotas = {k: int(v) for k, v in quotas.items()}

    rows = []
    for name, (role, files) in BOOKS.items():
        rows += build_book(name, files, quotas.get(name, 0), WIN.get(name))

    out = []
    for r in rows:
        ins = INSTR_CONT[int(hashlib.md5(r['ctx'][:100].encode('utf-8')).hexdigest(), 16) % len(INSTR_CONT)]
        gb = gloss_block(r['book'])
        out.append({"instruction": ins,
                    "input": (gb + '\n\n' + r['ctx']) if gb else r['ctx'],
                    "output": r['out'],
                    "metadata": {"book": r['book'], "chapter": str(r['chapter']),
                                 "task": "continue", "role": BOOKS[r['book']][0]}})

    # 大纲式（已归一化）。这批样本全部取自《灵境行者》，所以配灵境的专名表。
    # 同时补一段「硬约束」，结构与推理端一致（推理端放的是人物卡/设定卡，这里放该场景真实出现的人物名），
    # 目的是让模型见过这个段位，而不是把推理时多出来的段落当分布外。
    if os.path.isfile(a.outline):
        ol = [json.loads(l) for l in open(a.outline, encoding='utf-8') if l.strip()]
        gb = gloss_block('灵境行者')
        lj_names = GLOSSARY.get('灵境行者', [])
        for r in ol:
            r['metadata']['task'] = 'outline'
            r['metadata'] = {k: (str(v) if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False))
                             for k, v in r['metadata'].items()}
            hit = [n for n in lj_names if n in r['output']][:8]
            body = r['input']
            if hit:
                # 第二行是恒定声明：不编造任何事实，只让模型见过"这一段是硬约束"的形态。
                # 推理端同一位置放的是人物卡里的真实设定（如"右肩胛骨下可生出示例设定"）。
                hard = ('==== 硬约束（人物/设定/伏笔）====\n'
                        '【人物】' + '、'.join(hit) + '\n'
                        '【设定】按原著设定书写，不得改写角色的能力来源、位置与形态。')
                # 声线：只列**本段正文里真的出场了**的人物，避免整张表塞进去占预算。
                # 目的是让模型学到一条可迁移规则：「硬约束里写了谁怎么说话，正文就得那么写」。
                # 推理时用户的角色卡（含声线卡）放在同一位置，模型就会照做 ——
                # 用户要求"能分辨每个人的语气"，这一条此前完全没训练过。
                vl = voice_line(r.get('output', ''))
                if vl:
                    hard = hard + f'\n【人物声线】{vl}'
                body = body.replace('请写出这一幕的正文。', hard + '\n\n请写出这一幕的正文。')
            body = normalize_dash(body)
            out.append({"instruction": r['instruction'],
                        "input": (gb + '\n\n' + body) if gb else body,
                        "output": cap_at_sentence(normalize_dash(r['output']), 1500),
                        "metadata": r['metadata']})
        print(f'大纲式并入 {len(ol)} 条（已注入灵境专名块 + 硬约束段；超长按句末收口到 1500 字）')
    else:
        print(f'[WARN] 未找到归一化大纲式文件 {a.outline}')


# 多要点样本（相邻两幕：列出两个情节要点 -> 写出两段连续正文）
    # 专治「大纲里的爽点写不全」：原来训练样本全是"一个要点 -> 一段正文"，
    # 模型从没见过"一份要点清单 -> 连续多段正文"。
    if a.multibeat and os.path.isfile(a.multibeat):
        mb = [json.loads(l) for l in open(a.multibeat, encoding='utf-8') if l.strip()]
        for r in mb:
            r['metadata'] = {k: (str(v) if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False))
                             for k, v in r['metadata'].items()}
            out.append({"instruction": r['instruction'], "input": r['input'],
                        "output": normalize_dash(r['output']), "metadata": r['metadata']})
        print(f'多要点样本并入 {len(mb)} 条（两个要点 -> 连续两幕）')
    else:
        print(f'[WARN] 未找到多要点样本 {a.multibeat}')

    # 通用回放（防能力退化），配额不超过总量 2%
    if os.path.isfile(a.replay):
        rp = [json.loads(l) for l in open(a.replay, encoding='utf-8') if l.strip()]
        cap = max(10, int(len(out) * 0.02))
        rp = rp[:cap]
        for r in rp:
            r.setdefault('metadata', {})
            r['metadata']['task'] = 'general'
        out += rp
        print(f'通用回放并入 {len(rp)} 条')

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    # ---- 情绪浓度过滤 ----
    if a.emo_drop > 0:
        # ⚠️ 只作用于**续写**样本。
        # v15 的教训：把大纲样本一起削了（396→348），而大纲样本正是教"把要点写全"的那批，
        # 结果是治"AI 腔"的手段误伤了"要点覆盖"。
        cont = [r for r in out if r['metadata'].get('task') == 'continue']
        if cont:
            # ⚠️ 跳过「多人对白」样本。
            # v15 的教训：高情绪浓度样本里恰恰包含多人对白的感情戏，删掉后模型只会写主角一个人说话。
            protected = [r for r in cont if _speaker_count(r['output']) >= 2]
            pool = [r for r in cont if id(r) not in set(id(x) for x in protected)]
            scored = sorted(pool, key=lambda r: style_noise(r['output']))
            k = int(len(scored) * a.emo_drop)
            drop = set(id(r) for r in scored[-k:]) if k else set()
            print(f'  其中保护了 {len(protected)} 条多人对白样本（不参与剔除）')
            before = len(out)
            out = [r for r in out if id(r) not in drop]
            med_all = sum(style_noise(r['output']) for r in cont) / len(cont)
            kept = [r for r in cont if id(r) not in drop]
            med_kept = sum(style_noise(r['output']) for r in kept) / max(len(kept), 1)
            print(f'风格杂质过滤：剔除最高的 {a.emo_drop*100:.0f}%（{before-len(out)} 条），'
                  f'中位浓度 {med_all:.2f} -> {med_kept:.2f} /千字')

    with open(a.out, 'w', encoding='utf-8') as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'\n总样本 {len(out)} 条 -> {a.out}')
    print('任务分布:', dict(Counter(r['metadata'].get('task') for r in out)))
    print('书目分布:', dict(Counter(r['metadata'].get('book', '-') for r in out)))


if __name__ == '__main__':
    main()
