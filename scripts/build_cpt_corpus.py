# -*- coding: utf-8 -*-
"""构建 CPT（继续预训练）语料 —— 纯文本，next-token prediction 用

依据（用户 2026-09-15 指令 + 公开资料）：
  用户："拿本地的两本卖报的小说让模型全量泡进去，再加上《恐怖屋》和《玩家凶猛》
        增加样本量让模型会说人话，有人类的语言模型，《还剩三个月命》让模型学会
        人类的感情如何描绘。用最治本的方法。"
  → 保留 7B 基座（用户不相信小模型："它们可能连完整的基础逻辑都没有"）
  → 做 CPT，不做小模型

文献依据：
  - 「学习新的风格或体裁」只有 CPT 打勾（SFT 打不上）——Chris McCormick
  - CPT"特别适用于故事生成等强调语法和语言风格的场景"；SFT"不适用小说创作"
  - CPT 配方：LR 重热再衰减（约为原预训练 LR 的 10%）、混入少量原分布文本防遗忘、
    **CPT 之后必须补 SFT**（否则伤指令跟随）

数据格式（LLaMA-Factory 官方）：每行 {"text": "..."}，注册时 columns.prompt = text
"""
import os, sys, json, random, argparse

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

DS = r'<项目目录>\Datasets'
BOOK = r'<old-lib>'

# 书目 / 权重 / 角色（权重 = 采样倍数，用户给的分工）
#   灵境+大奉：主学卖报腔（本来体量最大，1.0 即可）
#   玩家凶猛+恐怖屋：增样本量、学"人话"（0.8 略降，因为它们不是卖报）
#   还剩三个月命：学情感描绘 —— 原始只有 0.17M 字，**必须加重**才起得到作用
PLAN = [
    # weight = **抽样倍数**（绝不能 >1）。路径用通配符，分卷文件会自动匹配。
    #
    # ── 卖报本人（核心风格锚）全量 ──────────────────────────
    ('灵境行者',         1.0, [os.path.join(BOOK, '《灵境行者》', '灵境行者*.txt')]),
    ('大奉打更人',       1.0, [os.path.join(BOOK, '《大奉打更人》', '大奉打更人*.txt')]),
    ('原来我是妖二代',   1.0, [os.path.join(BOOK, '参考', '原来我是妖二代*.txt')]),
    ('我的姐姐是大明星',  1.0, [os.path.join(BOOK, '参考', '我的姐姐是大明星*.txt')]),

    # ── 辅料 ──────────────────────────────────────────
    ('玩家凶猛',        0.5, [os.path.join(BOOK, '《玩家凶猛》', '玩家凶猛*.txt')]),
    # 恐怖屋提到 0.7：生活质感 4.6 是全语料最高，正是我们最缺的一项
    ('恐怖屋',          0.7, [os.path.join(BOOK, '参考', '我有一座恐怖屋*.txt')]),
    ('还剩三个月命',     1.0, [os.path.join(BOOK, '参考', '还剩三个月命*.txt')]),

    # ── 外部（2026-09-15 依"搜索 + 实测"双向验证后调整）────────
    # 超神机械师：搜到"文笔幽默""幽默风趣的行文" ✓ 现代口语 ✓ → 保留
    ('超神机械师',       0.20, [os.path.join(BOOK, '参考', '超神机械师*.txt')]),
    # 这游戏：搜到"论坛体" ✗ 特殊格式 → 降到 0.10
    ('这游戏也太真实了',  0.10, [os.path.join(BOOK, '参考', '这游戏也太真实了*.txt')]),
    # 惊悚乐园：搜到"融合大量 ACG 梗" ✗ 宅向语域 → 降到 0.10
    # 惊悚乐园：开篇整章是"物品数据库"（属性表不是叙事）→ 需要内容级清洗 ✓
    ('惊悚乐园',         0.10, [os.path.join(BOOK, '参考', '惊悚乐园*.txt')], True),
    # 轮回乐园：搜到"综漫"（动漫穿越）✗ + 实测 3.7% 段落含动漫角色名 ✗
    #           + 它是外部占比的 63%（1522万字）→ **整本不用**
    # ('轮回乐园',      0.00, [...]),

    # ── 新增（待用户提供，缺文件会自动跳过）────────────────────
    # 生活系游戏：搜到"文风治愈，烟火气十足""通过家常菜串联与家人朋友的温暖羁绊"
    #            → 补"生活质感 + 家庭日常"，题材（系统+美食+日常）离用户作品最近
    ('生活系游戏',       0.50, [os.path.join(BOOK, '参考', '生活系游戏*.txt')]),
    # 全职高手：搜到"非常成功的群像小说…有名有姓的角色50余人，女性也不会是花瓶"
    #          +"心理描写占比不足5%" → 补"群像 + 女性声线 + 情绪外化"（模型最弱的一项）
    ('全职高手',         0.50, [os.path.join(BOOK, '参考', '全职高手*.txt')]),
    # 我真是大明星：搜到"现象级爽白文，市井气浓厚" → 与番茄定位一致
    # 我真是大明星：体检后**大幅降权**（0.40 → 0.15）。
    # 它三项垫底：段方差 7118（全语料最极端）、连续同构 6.2（最高，而连续同构正是模型最像 AI 的一项）、
    # 用字丰富 13.1（最低）。只有『市井气』一个卖点，不值得拿最怕的三项去换。
    ('我真是大明星',     0.15, [os.path.join(BOOK, '参考', '我真是大明星*.txt')]),

    # ── 明确不收 ──────────────────────────────────────
    # 九州经   89万  收藏 300+，早期练笔
    # 临圣     48万  仙侠（语域不对）+ 连载中
]

CHUNK = 1500      # 每段的字数。cutoff_len 2048 token ≈ 3000 中文汉字，1500 留足余量；
                  # 再靠 packing 把短段拼满，不浪费上下文。


def read(p):
    """读文件；若 p 含通配符则把所有匹配文件拼起来（支持分卷）。"""
    if any(ch in p for ch in '*?['):
        import glob as _g
        parts = sorted(_g.glob(p))
        if not parts:
            return ''
        return ''.join(_read_one(f) for f in parts)
    return _read_one(p)


def _read_one(p):
    """走统一稳健读取（scan_noise.read_text）—— 严格解码 + 中文占比检查。
    旧的 errors='ignore' 写法对 GBK 文件永远不报错，导致 4 本书 98% 是乱码。"""
    from scan_noise import read_text
    return read_text(p)

def clean(t):
    """去章节标题行、空白行、**以及作者话/平台残留**。

    ⚠️ 2026-09-15 用户要求 + 实测发现的缺口：
    原版只去了「章标题行 + 空行」，**完全没过作者话** ——
    反查 cpt_v1 语料（452,221 行）发现真污染约 2100 行：
      ps：作者话 587（如"ps：这章少一点，不然十二点前无法更新了。"）
      码字相关   108（如"ps：庆祝一百万字！先改上一章错字，然后继续码字。"）
      求票求订    67 / 订阅数据 48 / 感言·站名·网址·盗版站 15
      分隔线 ----  1302
    这些混进去 = **教模型写作者话**，必须清干净。
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from scan_noise import HI, LO, PS_LINE   # HI=高精度（删）；LO=剧情合法（只统计）；PS_LINE=ps：行（不受长度保护）
    except Exception:
        HI = LO = None
    out, dropped = [], 0
    for line in t.split('\n'):
        s = line.strip()
        if not s:
            continue
        # 常见章节标题行：第X章 / 第X节 / 纯数字行
        if len(s) <= 24 and (s.startswith('第') and ('章' in s or '节' in s)):
            continue
        # 高精度污染 → 删（只删短行；长段落里出现这些词多半是正文）
        if HI is not None and ((len(s) <= 140 and HI.search(s)) or PS_LINE.search(s)):
            dropped += 1
            continue
        out.append(s)
    if dropped:
        print(f'    [净化] 剔除 {dropped} 行作者话/平台残留')
    return '\n'.join(out)


def _is_junk_chunk(t):
    """内容级清洗：属性数据块 / 动漫同人段落。
    行级正则只能抓"作者话"这类整行噪声；这两类是**内容性质**问题 ——
    惊悚乐园开篇整章是"物品数据库"（属性表，不是叙事）；
    轮回乐园会进入火影/海贼世界（动漫专名会把原创都市的语域带偏）。"""
    try:
        from scan_noise import is_stat_block, has_anime
        if is_stat_block(t):
            return True
        if has_anime(t, min_hits=2):
            return True
    except Exception as e:
        # ⚠️ 2026-09-16 修：原来这里是静默 `pass` —— 一旦导入/检查出错，
        #    内容级清洗会**悄悄不执行**，而整条流水线照样跑完、不报任何错 ✗
        #    （与"忽略警告"同一类病：静默失败最难发现）
        print(f'    [警告] 内容级清洗检查失败，本段按"不清理"处理：{type(e).__name__}: {e}')
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(DS, 'cpt_corpus.jsonl'))
    ap.add_argument('--seed', type=int, default=42)
    a = ap.parse_args()
    random.seed(a.seed)

    rows, stat = [], {}
    for item in PLAN:
        # 第 4 个字段 clean_junk（默认 False）—— 是否做内容级清洗
        # ⚠️ 只对"无限流/综漫"类书开：现代都市文本里出现"漫威/蜘蛛侠"是**合法语言** ✓
        #    第一版对所有书都开，结果误杀灵境 109 块系统面板 + 4 块含漫威的正常剧情 ✗
        name, weight, paths = item[0], item[1], item[2]
        clean_junk = item[3] if len(item) > 3 else False
        # ⚠️ 不能加 `if os.path.isfile(p)` —— 通配符路径（如 '惊悚乐园*.txt'）
        # 不是文件，会被过滤掉，导致整本书"读不到"。read() 自带读不到返回空。
        txt = ''.join(clean(read(p)) for p in paths)
        if not txt:
            print(f'[跳过] {name} 读不到')
            continue
        n_before = len(txt)
        # ⚠️ weight<1 时不能取整成 1 —— 那等于没降权。改成按比例抽样段数。
        reps = 1
        keep_ratio = min(1.0, float(weight))
        for r in range(reps):
            # 每次重复换一个起点，避免完全一致的切分
            off = (r * 7919) % CHUNK
            seg = txt[off:]
            # ⚠️ 抽样必须用"小数累加器"，不能用 n % round(1/ratio)。
            # 后者对 0.7 这种比例会失效：round(1/0.7)=1 → 取模恒为 0 → **全取** ✗。
            acc = 0.0
            for i in range(0, len(seg) - CHUNK, CHUNK):
                acc += keep_ratio
                if acc >= 1.0:
                    acc -= 1.0
                    piece = seg[i:i + CHUNK]
                    # 内容级清洗：仅对无限流/综漫类书启用（按书配置）
                    if clean_junk and _is_junk_chunk(piece):
                        continue
                    rows.append({'text': piece})
        stat[name] = (n_before, reps, len(rows))

    random.shuffle(rows)
    with open(a.out, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    total = sum(len(r['text']) for r in rows)
    print(f'\nCPT 语料 -> {a.out}')
    print(f'  共 {len(rows)} 段 / {total:,} 字（≈ {total/1000/1.6:.0f} 万 token 量级）')
    print('  各书贡献：')
    prev = 0
    for name, (n_before, reps, cum) in stat.items():
        print(f'    {name:<10} 原文字 {n_before:>9,} × {reps:>2} 倍 -> 累计段数 {cum-prev}')
        prev = cum
    print(f'\n  预估优化步数 ≈ {total/1.6/(8*2048):.0f} 步（batch 8 × cutoff 2048）')


if __name__ == '__main__':
    main()
