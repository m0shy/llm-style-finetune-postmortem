# -*- coding: utf-8 -*-
"""AI 味检测 —— 把「AI 味」变成一组有出处的数字

来源（都是搜到的公开资料，不是我拍的）：
  1. 骨朵网络影视访谈三位网文编辑（九州/麦芽/春田中文网）——AI 味五大特征：
     华美的空洞（形容词堆叠、开篇大段环境/神态描写）、逻辑 bug 经不起推敲…
  2. 今日头条《小说去高频词》（十年自媒体作者整理，取材 AIGC 检测机构公开报告 + 高校词频数据）
     ——给出中文网文专属的 AI 模板词清单（嘴角勾起/眼神深邃/心中一凛/沉吟片刻/顿时/瞬间/愈发…）
  3. 今日头条《6个指标检测AI味》（分析 200+ 条读者差评）——六项量化指标及阈值：
     句式重复（连续同构 ≤3）、词汇多样性（≥0.45，AI 0.34 / 人 0.52）、
     AI 高频词密度（≤5/千字，AI 12.3 / 人 1.1）、**段落长度方差（≥80，AI 32 / 人 165，"几乎零误判"）**、
     对话占比（30%~60%）、情绪词密度（≤8/千字，AI 14.6 / 人 3.2）
  4. 英文圈同源结论（斯坦福/图宾根研究：只看用词就能以 70%+ 准确率判别 AI）
     ——overused words / transition phrases / nominalization / 现在分词状语滥用

用法：
  python scripts/ai_tells.py 稿件.md                  # 默认两档基准并排（pre 成名前 + post 中段）
  python scripts/ai_tells.py 稿件.md --baseline-preset pre
  python scripts/ai_tells.py 稿件.md --dup-check      # 附加：与 09_草稿 既有章节查 ≥10 字连续重复
  python scripts/ai_tells.py --baseline               # 只算基准（按 preset / baseline-path）
  python scripts/ai_tells.py 稿件.md --baseline-path x.txt   # 自定义基准（优先级最高）

2026-10-12 改版（四件事）：
  1) metrics() 新增指标：对比句式/段首连接词/distinct-2,3/仿佛系比喻/网络用语/对话段占比，
     口径全部写在键名里（每千字 或 %）。口头禅告警是"列表型"指标（词+次数），单独走
     catchphrase_alerts()，不进 metrics() —— 基准要按块对每项数值取平均，列表没法平均。
  2) THRESH_PROJ 本项目参考档（与既有通用档并排输出，通用档一个不删），n=3 拟合待回验。
  3) 基准双档：--baseline-preset pre|post|both（默认 both）；--baseline-path 仍优先级最高。
  4) --dup-check 复读查重：目标稿 vs 09_草稿 既有章节（含 _工作台_*/ 的 AI原稿/交付稿），
     n-gram 集合交集，≥10 字连续重复，大文件分块扫。
"""
import os, re, sys, glob, statistics, argparse, collections

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ---- 中文网文专属 AI 模板词（来源 2）----
# 原则：**单个词出现没问题，同类词扎堆、固定句式反复复用才是判据**。所以看密度，不看有无比。
TELL_WORDS = [
    # 动作神态（"眼中闪过惊讶 + 嘴角上扬 + 心中了然"三连是标准 AI 缝合句）
    '嘴角勾起', '嘴角上扬', '嘴角微扬', '嘴角勾起', '眼神深邃', '眼中闪过一丝',
    '一丝惊讶', '微微挑眉', '挑了挑眉', '眉头微皱', '眉头紧锁', '沉吟片刻',
    '心中一凛', '心中一沉', '眼神一凝', '目光一凝', '眸光一闪', '神色一凛',
    '瞳孔微缩', '瞳孔骤缩', '神情复杂', '脸色一变', '嘴角抽搐',
    # 副词（来源 2 点名的网文 AI 副词）
    '顿时', '瞬间', '愈发', '略微', '一时之间', '缓缓', '徐徐',
    '微微', '淡淡', '轻轻', '默默', '静静',
    # 心理词（来源 2）
    '心中一动', '心下了然', '心中了然', '心中暗想', '心中暗道', '心中一喜',
    # 通用警报级连接词（来源 2）
    '与此同时', '然而', '此外', '值得注意的是', '毋庸置疑', '不可否认',
    '综上所述', '总而言之', '总的来说', '由此可见', '一言以蔽之',
    '至关重要', '举足轻重', '前所未有', '影响深远', '重中之重',
    '某种程度上', '在很大程度上',
    # 通用万能比喻（来源 2：千篇一律毫无新意）
    '双刃剑', '画卷', '灯塔', '桥梁', '基石', '里程碑',
]

# ---- 感官 / 闲笔词（来源 1、3：AI 缺闲笔与感官细节，人类多）——反向指标 ----
SENSE_WORDS = ['气味', '味道', '腥', '香', '臭', '烟味', '汗味', '潮湿', '干燥',
               '温度', '发烫', '冰凉', '刺骨', '闷热', '黏', '粗糙', '光滑',
               '声音', '响动', '窸窣', '吱呀', '轰', '嗡', '滴答',
               '光线', '影子', '阴影', '昏暗', '刺眼', '反光', '发白']

# ---- 2026-10-12 新增词表 / 句式（需求 1）----
# 对比句式：「不是…而是」「与其说…不如说」合计；…跨度限在同句内 20/30 字，防跨句误配
CONTRAST_PAT = re.compile(r'不是[^。！？…\n]{0,20}?而是|与其说[^。！？…\n]{0,30}?不如说')
# 段首连接词（拼接缝检测器：AI 把两段话缝在一起时最爱用这些开头。判读与基准比相对增幅，
# 不看绝对值——口语化文本天然也有段首"但/然后"）
PARA_CONNECTORS = ('但', '而', '可是', '不过', '只是', '然而', '所以', '因此',
                   '于是', '接着', '然后', '随后')
# 仿佛系比喻
SIMILE_WORDS = ['仿佛', '好像', '像是', '宛如', '如同', '恰似']
# 网络用语（本项目题材=自创作品，读者对滥用网络语敏感）
NET_SLANG = ['卧槽', '逗比', '牛逼', '傻逼', '离谱', '绝了', '麻了', '裂开', '破防',
             '上头', '整活', '摆烂', '社死', '加戏', '狗血']
CJK_ONLY = re.compile(r'[\u4e00-\u9fffA-Za-z0-9]{2,6}')   # 口头禅候选：2-6 字纯汉字/字母/数字
CJK_CHAR = re.compile(r'[\u4e00-\u9fff]')

SENT_SPLIT = re.compile(r'[。！？…]+')
QUOTE = re.compile(r'[“"]([^”"]{1,300})[”"]')

DUP_N = 10   # 复读查重：≥10 字连续片段（n-gram 长度）
DUP_DIR = r'<项目目录>\《自创作品》\09_草稿'   # 参照库（含 _工作台_*/ 子目录）


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


def longest_same_opening_run(sents, k=3):
    """最长连续「句首 k 字相同」的句子数（来源 3：连续同构不应超过 3）。"""
    runs, cur, prev = [], 1, None
    for s in sents:
        head = s.strip()[:k]
        if not head:
            prev, cur = None, 1
            continue
        if head == prev:
            cur += 1
        else:
            if prev is not None:
                runs.append(cur)
            prev, cur = head, 1
    if prev is not None:
        runs.append(cur)
    return max(runs) if runs else 0


def distinct_n(t, k):
    """distinct-k：字符二元/三元组的 type-token 比（%）＝去重后 k 元组数 / k 元组总数 × 100。
    只数汉字（滤标点/空白/换行），越大越多样；AI 复读腔典型偏低。"""
    cs = CJK_CHAR.findall(t)
    total = len(cs) - k + 1
    if total <= 0:
        return 0.0
    grams = {''.join(cs[i:i + k]) for i in range(total)}
    return len(grams) / total * 100


def metrics(t):
    n = max(len(t), 1)
    sents = [s for s in SENT_SPLIT.split(t) if s.strip()]
    paras = [p for p in t.split('\n') if p.strip()]
    # 段长（按字数）方差：来源 3 说这是"几乎零误判"的指标（AI 32 / 人 165）
    plens = [len(p) for p in paras]
    var = statistics.pvariance(plens) if len(plens) > 1 else 0.0
    # 句首 3 字重复率
    heads = [s.strip()[:3] for s in sents if len(s.strip()) >= 3]
    dup = 1 - (len(set(heads)) / max(len(heads), 1)) if heads else 0
    dlg = sum(len(m.group(1)) for m in QUOTE.finditer(t))
    # ---- 2026-10-12 新增（需求 1）----
    conn = sum(1 for p in paras if p.strip().startswith(PARA_CONNECTORS))
    return {
        '字数': len(t),
        'AI指纹词 每千字': round(sum(t.count(w) for w in TELL_WORDS) / n * 1000, 1),
        '其中网文模板词': round(sum(t.count(w) for w in TELL_WORDS[:40]) / n * 1000, 1),
        '情绪词 每千字': round(sum(t.count(w) for w in
                              ['心里一暖', '心中一暖', '心里一酸', '感到', '觉得', '意识到',
                               '心中', '内心', '心头'] ) / n * 1000, 1),
        '句首3字重复率%': round(dup * 100, 1),
        '最长连续同构句': longest_same_opening_run(sents),
        '段落长度方差': round(var, 0),
        '段落长度标准差': round(var ** 0.5, 1),
        '段数': len(paras),
        '对话占比%': round(dlg / n * 100, 1),
        '感官/闲笔 每千字': round(sum(t.count(w) for w in SENSE_WORDS) / n * 1000, 1),
        # ↓↓↓ 以下为 2026-10-12 新增键，既有键一个未动 ↓↓↓
        '对比句式 每千字': round(len(CONTRAST_PAT.findall(t)) / n * 1000, 1),
        '段首连接词%': round(conn / max(len(paras), 1) * 100, 1),
        'distinct-2%': round(distinct_n(t, 2), 1),
        'distinct-3%': round(distinct_n(t, 3), 1),
        '仿佛系比喻 每千字': round(sum(t.count(w) for w in SIMILE_WORDS) / n * 1000, 1),
        '网络用语 每千字': round(sum(t.count(w) for w in NET_SLANG) / n * 1000, 1),
        # 段落级口径：含中文引号的非空段 / 全部非空段（与上面字符级「对话占比%」并存）
        '对话段占比%': round(sum(1 for p in paras if ('“' in p or '”' in p))
                            / max(len(paras), 1) * 100, 1),
    }


def catchphrase_alerts(t, min_len=2, max_len=6, thresh=3):
    """口头禅告警（需求 1 最后一条）。列表型指标，不进 metrics()（基准分块要按数值平均）。

    口径：引号内文本的全部 2~6 字无标点子串，出现 >3 次（即 ≥4 次）即告警。
      · 整句引文恰 2~6 字 → 覆盖「2-6 字引号内短句」；
      · 长引文里反复出现的片段 → 覆盖「人物口头禅」。
    合并规则：若更长的串出现次数 ≥ 短串，短串视为长串的一部分，不重复告警。
    返回 [(词, 次数)]，按（次数, 词长）降序。人名高频入榜是正常的（名字复读本身就是 AI 味）。"""
    cnt = collections.Counter()
    for m in QUOTE.finditer(t):
        q = m.group(1)
        for L in range(min_len, max_len + 1):
            for i in range(len(q) - L + 1):
                s = q[i:i + L]
                if CJK_ONLY.fullmatch(s):
                    cnt[s] += 1
    hits = sorted(((w, c) for w, c in cnt.items() if c > thresh),
                  key=lambda x: (-x[1], -len(x[0])))
    out = []
    for w, c in hits:
        if any(w in w2 and c2 >= c for w2, c2 in out):
            continue
        out.append((w, c))
    return out


# 来源 3 给的阈值（AI 均值 / 人类均值 / 建议阈值）——通用档，保留作对照
THRESH = {
    'AI指纹词 每千字': (12.3, 1.1, 5.0, '低', '越低越像人'),
    '情绪词 每千字': (14.6, 3.2, 8.0, '低', '越低越像人'),
    '段落长度方差': (32, 165, 80, '高', '越高越像人'),
    '对话占比%': (None, None, (30, 60), '区间', '太少沉闷，太多像剧本'),
}

# —— 本项目参考档（2026-10-12 新增，需求 2）——
# 与上面通用档并存，输出两档并排；本项目档是拿本项目自己的 3 章样稿拟合的参考值，
# 样本极小（n=3），只当「这一章 vs 项目自身水位」的相对标尺，不要当普适阈值。
THRESH_PROJ = {
    '段落长度方差': (400, '高', '稳定期参考；开篇章节奏未铺开、绝对值天然偏低，用本稿开篇切片自校准（见输出「自校准」行）'),  # 参考值，n=3拟合待回验
    '对话段占比%': ((40, 46), '区间', '参考带（段落级）'),  # 参考值，n=3拟合待回验
}


def dup_fragments(tset, ref, n=DUP_N, chunk=400000):
    """在 ref 里找与 tset（目标稿 n-gram 集合）相交的连续重复片段。

    大文件分块扫：块间回退 n-1 字避免跨界漏配、又不会重复计数。
    ref 侧相邻命中（位置连续）合并成最大片段；纯标点/空白伪重复（整行省略号之类）要求
    至少含 5 个汉字才算数。返回按出现顺序的片段文本列表（每条 ≥n 字）。"""
    hits, L, start = [], len(ref), 0
    while start < L:
        end = min(start + chunk, L)
        base = start - (n - 1) if start > 0 else 0
        seg = ref[base:end]
        j0 = (start - base) if start > 0 else 0   # 后续块跳过与上一块重叠的 n-1 个位置
        for j in range(j0, len(seg) - n + 1):
            if seg[j:j + n] in tset:
                hits.append(base + j)
        start = end
    frags = []
    for p in hits:   # hits 升序；ref 侧位置连续的命中并入同一片段
        if frags and p == frags[-1][1] + 1:
            frags[-1][1] = p
        else:
            frags.append([p, p])
    return [ref[s:e + n] for s, e in frags
            if sum(1 for c in ref[s:e + n] if '\u4e00' <= c <= '\u9fff') >= 5]


def dup_check(target_path, t):
    """复读查重（需求 4）：目标稿 vs 09_草稿 既有章节（递归，含 _工作台_*/ 的 AI原稿/交付稿）。"""
    print(f'----- 复读查重（≥{DUP_N} 字连续重复，n-gram 集合交集）-----')
    root_abs = os.path.abspath(DUP_DIR)
    tgt_abs = os.path.abspath(target_path)
    refs = []
    for dp, _, fns in os.walk(root_abs):
        for f in fns:
            if not f.lower().endswith(('.md', '.txt')):
                continue
            p = os.path.abspath(os.path.join(dp, f))
            if p == tgt_abs or (os.path.isdir(tgt_abs) and p.startswith(tgt_abs + os.sep)):
                continue   # 排除本稿自身（target 为目录时排除其下所有文件，防自比）
            refs.append(os.path.join(dp, f))
    if not refs:
        print(f'  参照库为空：{DUP_DIR}（已排除本稿自身），跳过')
        return
    print(f'  参照库：{DUP_DIR}（{len(refs)} 个文件，已排除本稿自身；含 _工作台_*/ 子目录）')
    t = t.replace('\r\n', '\n').replace('\r', '\n')
    tset = {t[i:i + DUP_N] for i in range(len(t) - DUP_N + 1)}
    seen = {}   # 片段文本 -> [出现次数, 首个来源]
    for rp in refs:
        ref = read_any(rp)
        if not ref:
            continue
        ref = ref.replace('\r\n', '\n').replace('\r', '\n')
        for frag in dup_fragments(tset, ref):
            if frag in seen:
                seen[frag][0] += 1
            else:
                seen[frag] = [1, os.path.relpath(rp, root_abs)]
    if not seen:
        print('  ✅ 未发现 ≥10 字连续重复')
        return
    items = sorted(seen.items(), key=lambda kv: (-len(kv[0]), -kv[1][0]))
    total = sum(v[0] for v in seen.values())
    print(f'  最长重复：{len(items[0][0])} 字；去重后 {len(items)} 条 / 原始 {total} 处')
    for frag, (cnt, src) in items[:30]:
        disp = frag if len(frag) <= 60 else frag[:60] + '…'
        print(f'  [{len(frag)}字]{" ×%d" % cnt if cnt > 1 else ""} 〈{disp}〉 @ {src}')
    if len(items) > 30:
        print(f'  …（其余 {len(items) - 30} 条略）')


def _build_baseline(paths):
    """基准按 6000 字一块取 40 块平均，避免整本一次算（方差随长度变化）。口径沿用 v1。"""
    base = ''.join(read_any(p) for p in paths if os.path.isfile(p))
    if not base:
        return None, 0
    chunks = [base[i:i + 6000] for i in range(0, len(base) - 6000, max(6000, len(base) // 40))][:40]
    if not chunks:
        return None, 0
    per = [metrics(c) for c in chunks]   # 2026-10-12：一次算完再平均（v1 是每键重复算 40 遍，纯浪费）
    return {k: statistics.mean(pc[k] for pc in per) for k in per[0]}, len(chunks)


def _cell(x):
    return f'{x:>10.1f}' if isinstance(x, (int, float)) else f'{"—":>10}'


def _rel_note(v, b):
    if b is None:
        return '（无基准可对照）'
    if b <= 0:
        return '✅ 与基准同为 0' if v <= 0 else f'⚠️ 基准为 0，本文 {v}'
    return '✅ 不高于基准' if v <= b else f'⚠️ 为基准 ×{v / b:.1f}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', nargs='?')
    ap.add_argument('--baseline', action='store_true', help='只算基准（不测稿）')
    ap.add_argument('--baseline-path', nargs='+', help='基准 txt（优先级最高，覆盖 --baseline-preset）')
    ap.add_argument('--baseline-preset', choices=['pre', 'post', 'both'], default='both',
                    help='基准档：pre=成名前语料（妖二代/我的姐姐是大明星）；'
                         'post=大奉/灵境中段；both=两档并排（默认）')
    ap.add_argument('--dup-check', action='store_true',
                    help='附加：目标稿与 09_草稿 既有章节做 ≥10 字连续重复比对')
    a = ap.parse_args()

    PRE = [('pre(成名前)', [r'<old-lib>\其他参考小说\原来我是妖二代.txt',
                            r'<old-lib>\其他参考小说\我的姐姐是大明星.txt'])]
    POST = [('post(中段)', [r'<old-lib>\《灵境行者》\灵境行者(501-1000章).txt',
                            r'<old-lib>\《大奉打更人》\大奉打更人(501-955章).txt',
                            r'<old-lib>\《灵境行者》\灵境行者.txt',
                            r'<old-lib>\《大奉打更人》\大奉打更人(501-955章).txt'])]
    if a.baseline_path:                       # 优先级最高：显式指定基准文件
        presets = [('自定义', a.baseline_path)]
    elif a.baseline_preset == 'pre':
        presets = PRE
    elif a.baseline_preset == 'post':
        presets = POST
    else:
        presets = PRE + POST

    print('===== AI 味检测 =====')
    if a.baseline:
        for tag, paths in presets:
            bm, nch = _build_baseline(paths)
            print(f'\n--- 基准[{tag}] ---')
            if bm is None:
                print('  找不到基准文件，跳过')
                continue
            print(f'（{nch} 块 × 6000 字；阈值来源见文件头注释）')
            for k, v in bm.items():
                print(f'  {k:<18}{v:>10.1f}')
        return

    if not a.path:
        ap.error('需要稿件路径（或 --baseline）')
    t = read_any(a.path)
    if not t:
        print(f'读不到内容：{a.path}')
        return
    m = metrics(t)
    bases, tags = [], []
    for tag, paths in presets:
        bm, _ = _build_baseline(paths)
        bases.append(bm)
        tags.append(tag)
    if all(b is None for b in bases):
        print('⚠️ 找不到任何基准文件，基准列以 — 显示\n')

    def bget(k):
        vals = [b[k] for b in bases if b and k in b]
        return statistics.mean(vals) if vals else None

    lbl = '基准(' + '/'.join(tags) + ')' if len(tags) > 1 else '基准' + tags[0]
    print(f'（基准：{lbl}；阈值=通用档(来源见头注释) + 本项目参考档(THRESH_PROJ，n=3拟合待回验)）\n')
    print(f'{"指标":<16}' + ''.join(f'{tg:>10}' for tg in tags) + f'{"本文":>10}  判定 / 说明')
    rows = ['AI指纹词 每千字', '其中网文模板词', '情绪词 每千字', '句首3字重复率%',
            '最长连续同构句', '段落长度方差', '对话占比%', '对话段占比%',
            '感官/闲笔 每千字', '对比句式 每千字', '段首连接词%',
            'distinct-2%', 'distinct-3%', '仿佛系比喻 每千字', '网络用语 每千字', '字数']
    for k in rows:
        v, b = m.get(k, 0), bget(k)
        note = ''
        if k == 'AI指纹词 每千字':
            note = '✅ 比人还克制' if v < THRESH[k][1] else ('✅ 在人类区间' if v <= THRESH[k][2]
                                                          else ('⚠️ 偏高' if v < THRESH[k][0] else '❌ 达 AI 均值'))
        elif k == '情绪词 每千字':
            note = '✅ 在人类区间' if v <= THRESH[k][2] else ('⚠️ 偏高' if v < THRESH[k][0] else '❌ 达 AI 均值')
        elif k == '段落长度方差':
            g = '✅ 像人' if v >= THRESH[k][2] else ('⚠️ 偏均匀' if v > THRESH[k][0] else '❌ 达 AI 均值')
            p = '✅ ≥400' if v >= THRESH_PROJ[k][0] else '⚠️ <400'
            note = f'通用档:{g} | 项目档:{p}（稳定期参考；开篇章用开篇切片自校准）'
        elif k == '最长连续同构句':
            note = '✅ 合格' if v <= 3 else f'❌ 连续 {v} 句同构（阈值 3）'
        elif k == '对话占比%':
            note = '✅ 在区间' if 30 <= v <= 60 else ('偏低' if v < 30 else '偏高（像剧本）')
        elif k == '对话段占比%':
            g = '✅ 在区间' if 30 <= v <= 60 else ('偏低' if v < 30 else '偏高')
            p = '✅ 在参考带' if 40 <= v <= 46 else '⚠️ 出参考带'
            note = f'通用档:{g}(段级) | 项目档40-46:{p}（参考带）'
        elif k == '感官/闲笔 每千字':
            note = '✅ 高于基准' if (b is not None and v >= b) else '⚠️ 低于基准（AI 缺闲笔的典型症状）'
        elif k == '对比句式 每千字':
            note = _rel_note(v, b)
        elif k == '段首连接词%':
            note = (f'拼接缝检测器：为基准 ×{v / b:.1f}（判读看相对增幅，不看绝对值）'
                    if b else '拼接缝检测器（无基准可对照）')
        elif k in ('distinct-2%', 'distinct-3%'):
            note = ('✅ 高于基准（字符多样性够）' if (b is not None and v >= b)
                    else ('⚠️ 低于基准（字符多样性不足）' if b is not None else '（无基准可对照）'))
        elif k == '仿佛系比喻 每千字':
            note = _rel_note(v, b)
        elif k == '网络用语 每千字':
            note = _rel_note(v, b)
        print(f'{k:<16}' + ''.join(_cell(b[k]) if b and k in b else _cell(None) for b in bases)
              + _cell(v) + '  ' + note)

    # 开篇切片自校准（需求 2）：项目档 400 是稳定期参考；本稿三等分切片的段长方差给出自身水位
    paras = [p for p in t.split('\n') if p.strip()]
    if len(paras) >= 6:
        third = max(len(paras) // 3, 2)
        slices = paras[:third], paras[third:2 * third], paras[2 * third:]
        sv = [statistics.pvariance([len(p) for p in s]) if len(s) > 1 else 0.0 for s in slices]
        print(f'\n自校准（本稿段落三等分切片的段落长度方差）：{sv[0]:.0f} / {sv[1]:.0f} / {sv[2]:.0f}'
              f'  ←— 项目档 400 为稳定期参考，开篇章以切片值对照')

    alerts = catchphrase_alerts(t)
    print(f'\n----- 口头禅告警（引号内 2-6 字短句/口头禅，出现>3 次告警；列前 20）-----')
    if alerts:
        for w, c in alerts[:20]:
            print(f'  “{w}” ×{c}')
        if len(alerts) > 20:
            print(f'  …（其余 {len(alerts) - 20} 条略）')
    else:
        print('  无（无出现 >3 次的 2-6 字引号内短句）')

    if a.dup_check:
        print()
        dup_check(a.path, t)

    print('\n注：单个词出现没问题，**同类词扎堆、固定句式反复复用**才是判据 —— 所以看密度与连续次数，不看有无。')
    print('这套指标只覆盖"可量化"的部分。编辑判 AI 稿还有两条量不出来：逻辑 bug（人设/时空矛盾）与'
          '华美空洞（形容词堆叠但无实指），那两条必须人读。')


if __name__ == '__main__':
    main()
