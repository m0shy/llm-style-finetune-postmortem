# -*- coding: utf-8 -*-
"""大纲扩充器（带"后文约束"）—— 直连你的 Obsidian 大纲库

核心设计（针对"大纲省略太多、扩充必须知道后文"）：
  每次生成都注入三段信息：
    ① 本次要写的章节大纲
    ② 后文走向（后续 2~3 章的章级摘要）—— 只用于对齐，严禁提前写出
    ③ 相关约束（伏笔台账 / 跨循环传递清单 / 涉及人物与设定文件）
  这样模型才知道「这一笔要为什么服务」，不会写出跟后文打架的内容。

用法:
  # 看大纲（不调用模型）
  python scripts/outline_expand.py --volume "第一卷 校园暗战" --list

  # 生成第 5 章
  python scripts/outline_expand.py --volume "第一卷 校园暗战" --chapter 5 ^
      --api-base http://localhost:8000/v1 --model Qwen2.5-7B-Lingjing ^
      --beats 4 --out ch05.md

  # 只打印将要发送的 prompt（自检用）
  python scripts/outline_expand.py --volume "第一卷 校园暗战" --chapter 5 --dry-run
"""
import os, re, sys, io, json, random, argparse, time

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from outline_lib import load_all, next_chapters, read

VAULT = r'<项目目录>\《自创作品》'
PLOT = os.path.join(VAULT, '04_剧情')


# 训练端用的人物声线表（抽取自《灵境行者》文风最终报告的人物谱系，
# 属源书内容，不含用户世界观）。目的是让模型学到一条**可迁移的规则**：
# 「硬约束里写了某个人怎么说话，正文里就得那么写」。
# 推理时把用户自己的角色卡（含声线卡）放在同一位置，模型就会照做。
VOICE = {
    '张元清': '玩世不恭的高智商吐槽流，爱腹诽；嘴上认怂、心里腹诽、手上半推半就',
    '关雅': '冷静狙击，荤段子老司姬',
    '傅青阳': '淡淡道装逼金句',
    '夏侯傲天': '中二，"身为主角的我"',
    '赵城隍': '冷峻算计',
    '寇北月': '憨直强运',
    '外婆': '泼辣，"打断你的狗腿"式',
    '江玉饵': '撒娇卖萌，"mua~"',
    '孙淼淼': '俏皮甜美',
    '灵钧': '风流吐槽',
    '陈薇': '泼辣直给',
    '止杀宫主': '疯批撩拨，嗓音悦耳式撩人',
    '三道山娘娘': '御姐威仪，清冷威压',
    '银瑶郡主': '软萌怂，举小喇叭小声吐槽',
}


def voice_line(text, limit=6):
    """只列**本段正文里真的出场了**的人物声线，避免整张表塞进去占预算。"""
    hits = [f'{n}={v}' for n, v in VOICE.items() if n in text]
    return '、'.join(hits[:limit])

SYS_RULES = (
    "你在续写一部番茄平台的都市暗线游戏题材商业网文。番茄口径：节奏 > 文笔，冲突 > 铺垫，落地 > 内耗。\n\n"
    "【开篇】前 300 字出核心冲突；1000 字内出首个爽点；禁大段世界观科普，世界观只由人物行动带出。\n"
    "【节奏】动作交锋、关键对白、转折揭晓放慢写细；赶路、吃饭、已交代信息一笔带过。\n"
    "【心理】情绪一律外化为动作与微表情，禁直陈；内心戏不得超过半页。\n"
    # 下面这条是**同场景对比实测**逼出来的：同一场戏，卖报本人写出来
    # 「直陈情绪 0.0 / 千字、比喻词 0.0 / 千字」，模型写出来「1.99 / 3.98」。
    # 原来只有抽象的「禁直陈」，模型照犯；所以这里点名具体词形与句式。
    "【克制动笔】情绪只准用动作、对白、留白承载。严禁出现「心里一酸/心中一暖/感到/意识到/"
    "明白了/松了一口气」这类把情绪说破的词；严禁「小心翼翼地/淡淡地/深深地」这类副词。\n"
    # ⚠️ 2026-09-15：把「少用比喻」这类**用量**要求改成**用法**要求。
    # 原因：用量要求本身就教了"每段均匀地用一点"，而 AI 味恰恰来自用法 ——
    # 实测卖报的修辞落点方差 0.95、峰值倍数 10.2，模型只有 0.51 / 8.1：
    # **卖报是憋着的（大部分地方干净，关键处一次连用几个），模型是摊平的。**
    "【修辞落点】比喻（仿佛/宛如/犹如/像是）、排比、升华句只在情绪或冲突的最高点用，"
    "其余地方一个都不用——宁可整页没有一个比喻，也不要每段都摆一个；不要段段收金句、不要每段都升华。\n"
    "【句式张弛】长短句按情绪走：紧张时短句连打，松弛时用长句铺开；"
    "严禁全篇句长均匀，严禁连续三句以上用同一个句式起头（「他不禁…」「她微微…」这类机械重复是 AI 的典型痕迹）。\n"
    # 这一条是 2026-09-15 搜了 AI 味资料后加的，针对**基座模型自带的写法习惯**。
    # 实测：训练语料本身的 AI 指纹词密度 1.1/千字（比卖报原著 1.5 还干净），
    # 但模型产出 2.1~3.3 —— 说明这些词是 Qwen 基座的固有习惯，不是学来的，
    # 所以**过滤数据治不了，只能在指令里点名禁止**。
    # 词表出处：今日头条《小说去高频词》（取材 AIGC 检测机构公开报告 + 高校词频数据），
    # 其中"嘴角勾起 + 眼神深邃 + 心中一凛"三连被点名为"标准 AI 缝合句"。
    "【禁 AI 腔套话】严禁这些网文 AI 高频词：嘴角勾起、嘴角上扬、眼神深邃、"
    "眼中闪过一丝、微微挑眉、沉吟片刻、心中一凛、心中一沉、心中一动、心下了然、"
    "顿时、瞬间、愈发、略微、一时之间。严禁形容词堆叠却不给实指（华美的空洞）。"
    "严禁连续三句以上用同一个句式起头。\n"
    "【收尾】每幕收尾留钩（对话中断/动作中断/信息不对称/金句），但严禁提前写出后续情节。\n"
    "【禁令】禁圣母、禁憋屈、禁降智、禁注水、禁设定倾倒、禁反派死于话多、禁战力崩坏、"
    "禁破折号、禁“欲知后事如何”。\n"
    "【归因安全】一切异常必须可归因于游戏机制/组织/能量规则，严禁写成鬼神显灵。\n"
    # 实测抓到过模型在正剧正文里吐出「(╯°□°）╯︵ ┻━┻」掀桌颜文字、「♂♂♂♂♀♀♀♀」性别符号、「你TM」。这类混入比错字更显眼，必须在指令里明令禁止。
    # ⚠️ 2026-09-15 用户纠正：网络用语是"雅俗共赏"里**俗**的那一面，不能压制，要**正确且克制地引用**。
    # 《灵境行者》本身就有网络用语（吐槽、流行语），那是它幽默感的来源 —— 禁掉等于把风格切掉一块。
    # 原写法"严禁…网络缩写与英文单词"错在两处：
    #   ① 把两件不同的事混在一起禁：颜文字/emoji/特殊符号是**非语言的东西**（该禁）；
    #      网络用语是**语言的一部分**（该用，只是要守规矩）。
    #   ② "禁"这个写法本身就教错方向 —— 风格问题从来不是"用不用"，而是"谁用、什么时候用、用多少、用得对不对"。
    "【网络用语·正确且克制】网络用语（吐槽、流行语）该用就用，但必须守四条："
    "① 只出现在人物口中，叙述语言保持干净；② 符合说话人的年龄、身份、场合（未成年妹妹与长辈不会用同一套词）；"
    "③ 克制：同一段里最多一处，不堆砌，同一个梗不重复；④ 用得准 —— 用当下通行的说法，不用过气的、不生造。"
    "严禁的是**非语言的东西**：颜文字、emoji、表情符号、特殊符号（╯°□°╯︵┻━┻ 这类），"
    "以及为省事写的字母缩写（yyds / zqsg 这类）—— 网络用语要用中文原词，不用字母缩写。\n"
    # 以下四条来自早期样本里的原始写作要求，恰好治「爽点不落地 / 跑题 / 直陈情绪」，
    # 做结构化重建时一度被我丢掉，现已并回单一事实来源（训练与推理共用）。
    "【逐条落实】给出的每个情节要点都要落到正文，包括人物的回忆与联想，不得遗漏。\n"
    "【不得增删】不得新增要点之外的转折或结局，不得编造原文没有的动作。\n"
    "【禁解剖心理】不得出现自我解说式的心理分析（如“这个不重要，重要的是…”）。\n"
    "【细节自生】环境、光影、声音、气味等细节须自行铺陈，不得只把要点换个说法。\n"
    "【输出】只输出正文，不要标题、不要说明、不要复述大纲。"
)


def read(p):
    for enc in ('utf-8', 'gbk'):
        try:
            return open(p, encoding=enc).read()
        except Exception:
            continue
    return ''


ANCHOR_FILE = r'<项目目录>\Datasets\专名锚点表.md'
# 与训练端**完全同格式**的专名块前缀（务必保持一致，否则 train != inference）
ANCHOR_PREFIX = '【本作专名·只能用这些名字】'
ANCHOR_EXTRA = ['示例设定A', '示例设定B', '示例设定C', '示例设定D', '示例设定E', '示例设定F', '示例设定S', '示例设定Q', '示例设定R']
ANCHOR_CARD_DIRS = (('02_人物', ()), ('07_势力', ()), ('06_副本', ()), ('05_物件', ()),
                    ('03_设定', ('设定大纲',)))


def load_anchor(cap=1200):
    """生成专名块。这是压住「术语串台」的主力。

    v5 评测的硬证据：训练时没有专名块，模型就学会无视它，
    直接搬《灵境行者》的人物（李东泽，该书 717 次）来填。
    所以训练端也注入了同格式的块（见 build_multi_dataset.py），
    这里必须输出一模一样的格式，模型才认得。
    """
    names = []
    for sub, skip in ANCHOR_CARD_DIRS:
        d = os.path.join(VAULT, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith('.md'):
                nm = fn[:-3]
                if nm in skip or nm in ('人物卡片',):
                    continue
                names.append(nm)
    for x in ANCHOR_EXTRA:
        if x not in names:
            names.append(x)
    return (ANCHOR_PREFIX + '、'.join(names))[:cap]


def parse_chapters(volume):
    """按卷名（模糊匹配）定位分卷，返回 (章字典, 原始文本)。

    排版兼容由 outline_lib 统一处理：
      第一卷    管道表格      | 12 | 内容…… | 爽点…… |
      第二~四卷 单元 + 条目   ### 【第X单元…】（第 a - b 章） + - **第 12 章**：内容……
    """
    vols = load_all()
    if not vols:
        raise SystemExit(f'大纲库未解析到任何分卷，请检查 {PLOT}')
    hit = None
    for v in vols:
        if volume in v['volume'] or v['volume'] in volume or \
           (volume.strip('第卷 ') and volume.strip('第卷 ') in v['volume']):
            hit = v
            break
    if hit is None:
        names = ' / '.join(v['volume'] for v in vols)
        raise SystemExit(f'找不到卷「{volume}」，现有：{names}')
    return hit, vols


def collect_constraints(volume, chapter_text):
    """把本章相关的人物/设定/物件/副本/势力文件拉进来当硬约束。

    匹配方式有两条（v3 评测暴露的问题）：
      ① [[wikilink]]（含 [[A|显示名]] 与 # 锚点）
      ② **卷面文字里直接出现的卡名**
    第二条很关键：大纲常常只写"示例角色12卸下面具"而不带 wikilink，
    旧版就抓不到人物卡 → 模型没有本作知识 → 拿《灵境行者》的名词硬凑（术语串台）。
    """
    links, disp = set(), set()
    for m in re.finditer(r'\[\[([^\]\|#]+)(?:#[^\]\|]*)?(?:\|([^\]]+))?\]\]', chapter_text):
        if m.group(1):
            links.add(m.group(1).strip())
        if m.group(2):
            disp.add(m.group(2).strip())

    # 能力/设定类关键词。命中的行必须优先保留。
    # 起因：v6 评测里模型写出"示例设定B从手心射出"，而主角卡里明明写着"右肩胛骨下可生出示例设定B"。
    # 查出来是我这个摘要函数的锅：它跳过了表格行，而那条事实正好在表格里；且只取开头 170 字。
    KEY_FACT = ('示例设定A', '示例设定B', '示例设定C', '示例设定D', '示例设定E', '示例设定F', '示例设定G', '权柄', '能力', '形态',
                '生理', '肩胛', '示例设定H', '示例设定I', '示例设定T', '禁忌', '不能', '严禁', '只能', '代价',
                # 声线类：用户要求"能分辨每个人的语气"，所以人物卡里的「声线卡」必须进摘要。
                # 加之前卡片只带出身份与能力，声线信息从来没进过 prompt。
                '声线', '高频词', '口头禅', '口吻', '语气', '说话')

    def _clean(p, cap):
        """抽取卡片的**关键设定摘要**：身份段 + 所有命中能力关键词的行。

        为什么不能只取开头：卡片的开篇多是氛围与灵感源流，真正的硬设定（能力来源、位置、
        禁忌）常常在表格里或靠后。只取开头会导致模型写错设定（v6 实测：示例设定B射错位置）。
        """
        b = re.sub(r'^---.*?---\s*', '', read(p), flags=re.S)

        def norm(s):
            s = re.sub(r'^[>#\-*\s]*', '', s)                 # 去标题/引用/列表符
            s = re.sub(r'\|', ' ', s)                          # 表格竖线转空格
            s = re.sub(r'\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]',
                       lambda m: (m.group(2) or m.group(1)).strip(), s)   # 去 wikilink 语法
            return re.sub(r'[*`]', '', s).strip()

        lead, facts = [], []
        for ln in b.split('\n'):
            s = norm(ln)
            if len(s) < 8:
                continue
            if any(k in s for k in KEY_FACT):
                facts.append(s)
            elif len(s) >= 12 and len(lead) < 3:
                lead.append(s)
        out, used = [], 0
        for s in facts[:6] + lead:                             # 设定事实优先
            if used + len(s) > cap:
                break
            out.append(s)
            used += len(s)
        return (' '.join(out) or b.strip())[:cap]

    # 称谓别名：大纲里常写"主角""二妹"而不写名字，只按卡名匹配会漏。
    ALIAS = {'别名A': '示例角色1', '别名B': '示例角色2'}
    alias_hit = {ALIAS[k] for k in ALIAS if k in chapter_text}

    got = []
    for sub, cap in (('02_人物', 420), ('03_设定', 260), ('05_物件', 200),
                     ('06_副本', 260), ('07_势力', 200)):
        d = os.path.join(VAULT, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.md'):
                continue
            name = fn[:-3]
            if name in ('人物卡片', '设定大纲'):
                continue
            if (name in links) or (name in disp) or (name in chapter_text) or (name in alias_hit):
                got.append((name, _clean(os.path.join(d, fn), cap)))

    # 伏笔台账与跨循环清单永远带上（防止写冲突）
    for nm, rel, cap in (('伏笔台账', ('08_伏笔', '伏笔台账.md'), 1500),
                         ('跨循环传递清单', ('08_伏笔', '跨循环传递清单.md'), 1000)):
        p = os.path.join(VAULT, *rel)
        if os.path.isfile(p):
            got.append((nm, _clean(p, cap)))
    return got


def build_prompt(volume, n, chapters, constraints, beat_idx=None, beat_total=None, nxt=None):
    cur = chapters[n]['outline']
    if nxt is None:
        nxt = []
        for k in range(n + 1, n + 4):
            if k in chapters:
                nxt.append(f'第{k}章：{chapters[k]["outline"]}')
    else:
        nxt = [f'第{k}章：{t}' for k, t in nxt]

    # 约束段做字符预算，避免 prompt 暴涨到训练长度的好几倍
    rest = [c for c in constraints if c[0] not in ('伏笔台账', '跨循环传递清单')]
    tail = [c for c in constraints if c[0] in ('伏笔台账', '跨循环传递清单')]
    picked, used = [], 0
    for name, body in rest:
        if used + len(body) > 1300:
            continue
        picked.append((name, body))
        used += len(body)
    picked += tail[:1]

    anchor = load_anchor()
    cons = '\n'.join(f'【{name}】{body}' for name, body in picked)
    part = f'（本次只写这一幕的第 {beat_idx}/{beat_total} 段，不要写完整章）' if beat_idx else ''
    return (
        f'{SYS_RULES}\n\n'
        f'{anchor}\n\n'
        f'==== 本次要写 ====\n'
        f'《{volume}》第{n}章{part}\n'
        f'章级大纲：{cur}\n'
        f'本章爽点闭环：{chapters[n].get("payoff", "") or "（见章级大纲）"}\n\n'
        f'==== 后文走向（仅供对齐，严禁提前写出）====\n'
        + ('\n'.join(nxt) if nxt else '（本章为卷末，无后文）') + '\n\n'
        f'==== 硬约束（人物/设定/伏笔）====\n{cons}\n\n'
        f'请写出这一幕的正文。'
    )


def split_beats(text, k):
    sents = [s.strip() for s in re.split(r'(?<=[。！？；])', text) if s.strip()]
    if not sents:
        return [text]
    k = max(1, min(k, len(sents)))
    size = (len(sents) + k - 1) // k
    return [''.join(sents[i:i + size]) for i in range(0, len(sents), size)]


def chat(api_base, model, prompt, temp, top_p, rep, ngram, max_new, timeout=180):
    import requests
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "temperature": temp, "top_p": top_p, "max_tokens": max_new,
            "repetition_penalty": rep, "no_repeat_ngram_size": ngram,
            "frequency_penalty": 0.3, "presence_penalty": 0.2}
    r = requests.post(api_base.rstrip('/') + '/chat/completions', json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--volume', required=True)
    ap.add_argument('--chapter', type=int)
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--beats', type=int, default=4)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--out', default=None)
    ap.add_argument('--api-base', default=os.environ.get('LLM_API_BASE', 'http://localhost:8000/v1'))
    ap.add_argument('--model', default=os.environ.get('LLM_MODEL', 'Qwen2.5-7B-ZhuanShu'))
    ap.add_argument('--temperature', type=float, default=0.65)
    ap.add_argument('--top-p', type=float, default=0.9)
    ap.add_argument('--repetition-penalty', type=float, default=1.1)
    ap.add_argument('--no-repeat-ngram', type=int, default=4)
    ap.add_argument('--max-new-tokens', type=int, default=900)
    a = ap.parse_args()

    hit, vols = parse_chapters(a.volume)
    chapters = hit['chapters']
    volume = hit['volume']
    vi = vols.index(hit)
    if not chapters:
        raise SystemExit(f'《{volume}》未解析到章级大纲，请检查该卷 md 的排版')
    if a.list:
        print(f'《{volume}》共 {len(chapters)} 章（声明 {hit.get("declared")}）：')
        for n in sorted(chapters):
            print(f'  第{n}章：{chapters[n]["outline"][:78]}')
        return
    if a.chapter is None or a.chapter not in chapters:
        raise SystemExit(f'请用 --chapter 指定章号（{min(chapters)}~{max(chapters)}）')

    nxt = next_chapters(vols, vi, a.chapter, 3)
    cons = collect_constraints(volume, chapters[a.chapter]['outline'])
    beats = split_beats(chapters[a.chapter]['outline'], a.beats)
    print(f'《{volume}》第{a.chapter}章 → {len(beats)} 个 beat；注入约束 {len(cons)} 份；后文 {len(nxt)} 章')

    if a.dry_run:
        print('=' * 80)
        print(build_prompt(volume, a.chapter, chapters, cons, 1, len(beats), nxt))
        return

    parts = []
    for i, _ in enumerate(beats, 1):
        prompt = build_prompt(volume, a.chapter, chapters, cons, i, len(beats), nxt)
        try:
            seg = chat(a.api_base, a.model, prompt, a.temperature, a.top_p,
                       a.repetition_penalty, a.no_repeat_ngram, a.max_new_tokens)
        except Exception as e:
            print(f'  !! beat{i} 失败: {e}')
            seg = ''
        print(f'  beat{i} {len(seg)} 字')
        parts.append(seg)
        time.sleep(0.2)
    text = '\n\n'.join(p for p in parts if p)
    out = a.out or f'ch{a.chapter:02d}.md'
    open(out, 'w', encoding='utf-8').write(text)
    print(f'\n已写出 {out}（{len(text)} 字）')
    print('提醒：拼接后需人工过一遍衔接；后文约束已在 prompt 中，若仍跑偏请检查该卷 md 的章级摘要是否够具体。')


if __name__ == '__main__':
    main()
