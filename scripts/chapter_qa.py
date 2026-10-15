# -*- coding: utf-8 -*-
"""章节质检闸门 —— 模型产出正文的交付前检查

为什么需要它：
  自动分只数句号、查词表，抓不到 v3 暴露的三类真问题。本工具把它们变成硬检查：
    ① 术语串台：正文里冒出《灵境行者》《大奉打更人》的专名（张元清 / 怀庆 / 天火宗 / 夜游神 …）
    ② 专名漂移：出现人物白名单（你的 02_人物 卡片）以外的疑似人名
    ③ 归因违规：把异常写成鬼神显灵（平台合规红线，异常必须归因于机制 / 组织 / 能量规则）
  外加你的个人禁用项与番茄档口径检查。

用法：
  python chapter_qa.py 生成稿.md
  python chapter_qa.py 生成稿.md --quiet     # 只打印结论行
"""
import os, re, sys, io, argparse
from collections import Counter

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass
VAULT = r'<项目目录>\《自创作品》'

# ---- 外来源头专名（灵境行者 / 大奉打更人），出现即为串台 ----
FOREIGN = {
    '灵境行者': ['张元清', '关雅', '傅青阳', '元始天尊', '五行盟', '太一门', '止杀宫', '阴尸',
                 '血蔷薇', '浅野凉', '姜精卫', '佘灵隧道', '夜游神', '天火长老', '天火宗', '山鬼',
                 '树王', '猴王', '龙崎一', '高峰长老', '夏侯傲天', '银瑶郡主', '星辰之主',
                 '魔眼天王', '恐惧天王', '色欲神将', '亡者归来', '白兰', '赵城隍', '九漏鱼',
                 '管中窥鲍', '牡丹仙子', '灵能会', '元始', '阴气', '蛊惑之妖', '百无禁忌'],
    '大奉打更人': ['许七安', '怀庆', '宋卿', '赵守', '魏渊', '洛玉衡', '楚元缜', '监正', '打更人',
                   '司天监', '云鹿书院', '桑泊', '巫神教', '万妖国', '九尾天狐', '金莲', '阿苏罗',
                   '李妙真', '神殊', '杨千幻', '镇北王', '元景帝', '大奉', '司铃', '问心阵'],
}

# ---- 归因安全红线（番茄：异常必须可归因于机制） ----
SPIRIT = ['显灵', '显圣', '神迹', '鬼神', '鬼魂', '冤魂', '投胎', '阴曹', '地府', '报应',
          '天罚', '天道昭昭', '神仙', '法力无边', '因果轮回', '阴德', '阳间', '阴间', '仙家']

# ---- 你的个人禁用项 ----
DASH = ['——', '—', '--']
BAGU = ['首先', '其次', '总而言之', '综上所述', '值得注意的是', '不禁', '不由得',
        '仿佛', '似乎', '深深地', '默默地', '长长地', '缓缓地', '心中一凛，暗道']

# ---- 古风污染（现代都市题材不该出现） ----
GUFENG = ['大人', '卑职', '在下', '公子', '妾身', '尔等', '客栈', '衙役', '银两', '稽首',
          '请安', '遵命', '兄台', '阁下', '本官', '钱庄', '轿子', '丫鬟', '贫道', '老夫',
          '晚辈', '岂敢', '惶恐', '失敬', '民女', '官人']

SPEECH = r'(?:道|说道|问道|笑道|冷笑|皱眉|点头|摇头|开口|出声|低声道|沉声道|喃喃)'

# 常见姓氏（用于"疑似人名"候选抽取；只做提示，不下判决）
SURNAMES = ('赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜谢邹喻柏窦章云苏潘葛'
            '范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮齐康伍'
            '余元卜顾孟平黄和穆萧尹姚邵汪祁毛狄贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席'
            '季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万柯管卢莫房裘解应宗丁宣邓'
            '郁单杭洪包诸左石崔吉龚程邢滑裴陆荣翁荀羊惠甄曲封芮储靳段富巫乌焦巴弓牧山谷车侯全班'
            '仲伊宫宁仇栾甘厉戎祖武符刘詹束龙叶幸司韶黎薄印宿白怀蒲从鄂索咸赖卓蔺屠蒙池乔阴胥苍'
            '闻党翟谭贡劳姬申扶堵冉雍桑桂牛寿通边燕浦尚农温别庄晏柴瞿阎充慕连茹习艾鱼容向古易慎'
            '戈廖庾终居衡步都耿满弘匡国文寇广禄欧沃利蔚越隆师巩聂晁融冷辛那简饶空曾沙养鞠须丰巢'
            '关蒯相查荆红游竺权盖益桓')

STOP_WORDS = {'王者', '王国', '王者荣耀', '历史', '于是', '结果', '同时', '随后', '顿时',
              '武侠', '文字', '文武', '天才', '天空', '白天', '明明', '江湖', '江水', '山东',
              '东南', '西边', '北上', '中华', '人生', '任务', '何必', '何况', '允许', '许多',
              '李子', '石头', '包住', '陈述', '张开', '程度', '方程', '柳树', '疏通', '雷霆',
              '雷锋', '容纳', '向阳', '古今', '实际', '步调', '众多', '任意', '无奈', '冷清',
              '戈壁', '融洽', '简便', '何必', '石破', '子孙', '叶子', '谭嗣', '关怀', '查探'}


BAD_TAIL = set('的了是在把和与而且但就是大继脸道想呢来着过说笑看走站坐起落问答总好新'
               '会能要可都也就又还只很太更最真更上下里外前后中')
LEFT_OK = set('，。！？；：、“”「」"\' \n\t（()）　·…')
SPEECH_HEAD = ('说道', '道：', '问道', '笑道', '冷笑', '皱眉', '点头', '摇头', '开口',
               '出声', '低声道', '沉声道', '喃喃', '看着', '看向', '站在', '坐在', '走了')


def suspect_names(text, whitelist):
    """姓氏法抽候选 + 同前缀变体检测（专名漂移的典型特征）。

    取词加两道约束压掉"于是 / 那边"这类假阳性：
      ① 候选处在"人名位"（行首或紧跟标点）；或
      ② 后面紧接说话 / 动作动词。
    """
    cand = Counter()
    for m in re.finditer(r'[' + SURNAMES + r']', text):
        i = m.start()
        left_ok = (i == 0) or (text[i - 1] in LEFT_OK)
        for L in (3, 2):
            w = text[i:i + L]
            if len(w) < L or not re.fullmatch(r'[\u4e00-\u9fff]+', w):
                continue
            if w in whitelist:
                break                       # 命中白名单，不再回退到短形式
            tail = text[i + L:i + L + 2]
            right_ok = any(tail.startswith(v) for v in SPEECH_HEAD)
            if not (left_ok or right_ok):
                continue
            if w[-1] in BAD_TAIL or w in STOP_WORDS:
                continue
            cand[w] += 1
            break

    # 漂移判据：共享「前两个字」的多个变体并存。
    # 不用"同姓氏"分组，因为本作里主角 / 示例角色1 / 示例角色2本就同姓，会误报。
    groups = {}
    for k in cand:
        groups.setdefault(k[:2], []).append(k)
    drift = {c: sorted(set(v)) for c, v in groups.items() if len(set(v)) >= 2}
    return cand, drift


# ---- 训练语料（查重用）：模型是从这些书学出来的，最怕它把原文整段吐出来 ----
SRC_HOME = r'<old-lib>'
SOURCES = {
    '灵境行者': [os.path.join(SRC_HOME, '《灵境行者》', n) for n in
                 ('灵境行者(1-500章).txt', '灵境行者(501-1000章).txt', '灵境行者(1001-1050章).txt')],
    '大奉打更人': [os.path.join(SRC_HOME, '《大奉打更人》', n) for n in
                   ('大奉打更人(1-500章).txt', '大奉打更人(501-955章).txt')],
    '玩家凶猛': [os.path.join(SRC_HOME, '《玩家凶猛》', '玩家凶猛.txt')],
    '恐怖屋': [os.path.join(SRC_HOME, '参考', '我有一座恐怖屋.txt')],
    '还剩三个月命': [os.path.join(SRC_HOME, '参考', '还剩三个月命，请让我从容赴死.txt')],
}
DUP_K = 20          # 连续多少字与源书完全一致就判为疑似复读
DUP_MIN_HAN = 15    # 且这 20 字里至少要有这么多实字，否则算标点撞车（误报）


def dup_check(text, k=DUP_K, min_han=DUP_MIN_HAN):
    """在源书里搜生成稿有没有连续 k 字以上的原文复读。

    为什么必须查：模型是从这五本书学出来的，容易在某些段落"背原文"。
    吐进你的书里既是抄袭，也踩番茄的 AI 合规红线（要求原创度）。

    为什么加了实字密度门槛：实测 v6 的 G2 稿曾被判"与《玩家凶猛》连续 14 字重合"，
    实际重合的是 `吗？”\\n　　“嗯。”\\n　　李` —— 全是标点、引号、换行，只有"李"一个实字。
    标点撞车不是复读，所以窗口里实字不够就跳过。
    """
    hits, clean = [], (text or '').strip()
    if len(clean) < k:
        return hits
    for name, files in SOURCES.items():
        corpus = ''
        for f in files:
            if os.path.isfile(f):
                corpus += read(f)
        if not corpus:
            continue
        for i in range(0, len(clean) - k + 1):
            win = clean[i:i + k]
            if len(re.findall(r'[\u4e00-\u9fff]', win)) < min_han:
                continue                      # 标点为主的窗口，跳过
            if win in corpus:
                j = i + k
                while j < len(clean) and clean[i:j + 6] in corpus:
                    j += 6
                hits.append((name, clean[i:min(j, i + 160)]))
                break
    return hits


def strip_dash(text):
    """把破折号换成不违反作者禁令的写法。

    为什么需要：源书（卖报原著）大量使用 `——`，模型学来了。
    实测 v6 的 C1/F1/G2 三个探针各出现 1 处（插入语 / 拟声拉长 / 停顿）。
    作者明令禁破折号，所以这一步必须做。

    替换规则（机械规则，方便按口味再调）：
      后面紧跟收尾引号或句末 → `……`（语气拉长 / 戛然而止）
      其余（插入语、同位语、揭晓） → `：`
    """
    def rep(m):
        nxt = text[m.end():m.end() + 1]
        return '……' if (nxt == '' or nxt in '”"」』\n。！？，；') else '：'
    return re.sub(r'——|—|--', rep, text)


def read(p):
    for enc in ('utf-8', 'gbk'):
        try:
            return __import__('scan_noise').read_text(p)
        except Exception:
            continue
    return ''


def load_whitelist(vault=VAULT):
    names, d = set(), os.path.join(vault, '02_人物')
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.endswith('.md') and fn not in ('人物卡片.md',):
                names.add(fn[:-3])
                body = __import__('scan_noise').read_text(os.path.join(d, fn))
                for m in re.finditer(r'(?:别名|称呼|绰号)[：:]\s*([^\n]{1,40})', body):
                    for t in re.split(r'[、,，/|\s]+', m.group(1)):
                        t = t.strip(' 　*「」"“”')
                        if 2 <= len(t) <= 4:
                            names.add(t)
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--dup', action='store_true',
                    help='对五本源书做原文查重（较慢，约 1 分钟）')
    a = ap.parse_args()

    text = __import__('scan_noise').read_text(a.path)
    body = text.strip()
    wl = load_whitelist()
    issues = []

    # ① 术语串台
    foreign_hits = {}
    for book, terms in FOREIGN.items():
        hit = [t for t in terms if t in body]
        if hit:
            foreign_hits[book] = hit
            issues.append(f'术语串台（{book}）：' + '、'.join(hit))

    # ② 专名漂移
    sus, drift = suspect_names(body, wl)
    for c, vs in sorted(drift.items()):
        issues.append(f'专名漂移嫌疑：以「{c}」开头的 {len(vs)} 个不同人名并存 → ' + '、'.join(vs))
    if sus:
        top = sorted(sus.items(), key=lambda x: -x[1])[:12]
        issues.append('疑似未登记人名（已在白名单外的，需人工确认是漂移还是新角色）：'
                      + '、'.join(f'{k}x{v}' for k, v in top))

    # ③ 归因安全
    sp = [w for w in SPIRIT if w in body]
    if sp:
        issues.append('归因违规风险：' + '、'.join(sp))

    # ④ 个人禁用与口径
    dsh = len(re.findall(r"——|—|--", body))  # 按"破折号出现次数"计，不是按字符数
    if dsh:
        issues.append(f'破折号 x{dsh}')
    gf = [w for w in GUFENG if w in body]
    if gf:
        issues.append('古风词污染：' + '、'.join(gf))
    bg = [w for w in BAGU if w in body]
    if bg:
        issues.append('八股词：' + '、'.join(bg))

    # ⑤ 半角标点混入（中文语境里的 . , ! ?）
    half = len(re.findall(r'[\u4e00-\u9fff][.,!?;:]', body))
    if half:
        issues.append(f'半角标点混入 x{half}')

    # ⑥ 复读
    sents = [s.strip() for s in re.split(r'[。！？\n]+', body) if len(s.strip()) > 4]
    dup = len(sents) - len(set(sents))
    if sents and dup / len(sents) > 0.08:
        issues.append(f'复读偏高 {dup}/{len(sents)}')

    # ⑦ 番茄档：前 300 字内是否有冲突信号
    head = body[:300]
    CONFLICT = ['！', '？', '“', '突然', '猛然', '却', '竟', '死', '血', '杀', '砸', '吼', '怒吼', '吼叫']
    if not any(c in head for c in CONFLICT):
        issues.append('开篇 300 字内未见明显冲突信号（番茄档要求）')

    # ⑧ 原文查重（慢，需 --dup 显式开启）
    if a.dup:
        import time
        t0 = time.time()
        print('  正在对五本源书做原文查重……')
        for name, seg in dup_check(body):
            issues.append(f'原文复读（{name}，连续 {DUP_K} 字以上重合）：{seg[:60]}……')
        print(f'  查重完成，用时 {time.time()-t0:.0f}s')

    # ⑧ 结构指标
    paras = [p.strip() for p in body.split('\n') if p.strip()]
    plens = [len(p) for p in paras] or [0]
    stat = (f'字数 {len(body)} · 段数 {len(paras)} · 段长中位 {sorted(plens)[len(plens)//2]} · '
            f'句数 {len(sents)} · 复读句 {dup}')

    print(f'\n=== 质检：{os.path.basename(a.path)} ===')
    print(stat)
    if issues:
        print(f'\n发现 {len(issues)} 类问题：')
        for i, s in enumerate(issues, 1):
            print(f'  {i}. {s}')
    else:
        print('\n未发现本文所列问题。')
    print(f'\n结论：{"需人工复核" if issues else "通过"}')

    if not a.quiet:
        print('\n提示：本工具只查硬性指标与词表，抓不出"腔调同源""意象复用""描绘缺位"这类质感问题，'
              '交付前仍须人工通读。')


if __name__ == '__main__':
    main()
