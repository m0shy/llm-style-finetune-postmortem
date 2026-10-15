# -*- coding: utf-8 -*-
"""字级崩坏检测 —— 抓「怀Celel」「怀慶」这类字级错误

为什么需要：这是唯一长期没有自动检测工具的一类问题，全靠人工读才发现。
  实际遇到过的：
    - `怀**Celel**顿了一下`（混进拉丁字母）
    - `怀**慶**声音低沉`（混进繁体字）
    - `示例角色14**县**起锐利的目光`（应为"泛起/抬起"）
    - `堂主**任**如疯狗`（凭空多一个"任"）
    - `示**列**角色4`（人名同音错字）

设计取舍（重要）：
  默认只跑**高精度**信号 —— 它们几乎不误报，可以直接当闸门用：
    ① 拉丁字母串混进正文     ② 繁体字混进简体正文
    ③ 日文假名 / 韩文混入     ④ 同字连续 3 次以上     ⑤ 半角标点混入
  另有一个 `--bigram` 的**实验性**信号（二字组合未见于源语料）。
  实测它**精度不够**：即使把源语料切成 1300 万字的二字组合表、并排除本作专名，
  正常文本里"跨词边界"的组合（会山、意躺、色鞭…）依然会被大量误报，
  一段 127 字的样本就出 9 条。所以它默认关闭，只在你愿意人工筛的时候启用。

用法：
  python scripts/typo_check.py 稿件.md
  python scripts/typo_check.py 章节目录/            # 目录下所有 .md 都查
  python scripts/typo_check.py 稿件.md --bigram     # 附带低精度候选清单
"""
import os, re, sys, json, argparse, collections

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

DS = r'<项目目录>\Datasets'
CACHE = os.path.join(DS, 'data_dual', 'bigram_cache.json')
VAULT = r'<项目目录>\《自创作品》'
CARD_DIRS = ('02_人物', '03_设定', '05_物件', '06_副本', '07_势力')
SRC_HOME = r'<old-lib>'

# ① 设定里本来就有的字母/数字，不算崩坏
WHITELIST_ASCII = ('NPC', 'SSS')

# ② 繁体写法表。**只收简体/繁体写法不同的字** ——
#    像「利」「值」「史」「西」「南」「北」「音」这些两边同形，收进来就是误报。
TRAD_ONLY = set(
    '慶來說個們這時對於後現實學國會車東馬鳥龍門長開關見話語讀書寫產業廣為無爾亞'
    '麼樣幾燈閃終將體覺應該歡樂兒頭臉處點線飛風雲霧電氣價讓認識錯節運權經濟繼續歷'
    '萬與觀資買賣機靜聲響醫療藥網頁號碼標準鳳鷹獸鏡劍槍彈裝'
)

# 本作人名（用于 ①b 的人名变体检测），运行时由 load_user_names 填充
NAMES = set()

# ④ 拟声词白名单：这些字连续出现是正常的（砰砰砰 / 咚咚咚 / 哈哈哈），不算崩坏
ONOMATOPOEIA = set('砰咚哈呼啪哗滋嗡叮当咔嘀轰隆轰嘟哔滋嚓哐咣呲唰嘶嗯嘿喂唉哎哦噢哈噗嗤咯噔')

# ①c 异常符号黑名单：只盯这几个 Unicode 区段，精确、几乎不误报。
#   框线/方块/几何/杂项符号/带圈字符/字母式符号/组合用附标/度数符号/性别符号/古文字
ABNORMAL = re.compile(
    r'[\u2500-\u257f\u2580-\u259f\u25a0-\u25ff\u2600-\u27bf'
    r'\u2b00-\u2bff\u2460-\u24ff\u2100-\u214f\ufe30-\ufe4f'
    r'\u00b0\u2640\u2642\u3007]')

# ③ 半角标点（中文正文里不该出现）
HALF_PUNCT = re.compile(r'[,;:!?](?![0-9A-Za-z])')


def read(p):
    for enc in ('utf-8', 'gbk'):
        try:
            return __import__('scan_noise').read_text(p)   # 2026-09-16 统一修缮：原 errors='ignore' 对 GBK 静默出错
        except Exception:
            continue
    return ''


def load_bigrams():
    """实验性信号用：五本源书的二字组合表（按标点切分，不跨标点）。"""
    if os.path.isfile(CACHE):
        try:
            return set(json.load(open(CACHE, encoding='utf-8')))
        except Exception:
            pass
    files = [
        os.path.join(SRC_HOME, '《灵境行者》', '灵境行者(1-500章).txt'),
        os.path.join(SRC_HOME, '《灵境行者》', '灵境行者(501-1000章).txt'),
        os.path.join(SRC_HOME, '《大奉打更人》', '大奉打更人(1-500章).txt'),
        os.path.join(SRC_HOME, '《玩家凶猛》', '玩家凶猛.txt'),
        os.path.join(SRC_HOME, '参考', '我有一座恐怖屋.txt'),
    ]
    grams = set()
    for f in files:
        if not os.path.isfile(f):
            continue
        for seg in re.split(r'[^\u4e00-\u9fff]+', read(f)):
            grams.update(seg[i:i + 2] for i in range(len(seg) - 1))
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(sorted(grams), open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
    return grams


def load_user_names():
    """本作专名，供实验性信号做白名单。"""
    names = ['示例设定A', '示例设定B', '示例设定C', '示例设定D', '示例设定E', '示例设定F', '主角', '示例角色14',
             '示例角色12', '示例角色1', '示例角色2', '示例角色7', '示例角色6', '示例角色3', '示例角色8',
             '示例角色11', '示例设定S', '示例设定K', '示例设定H', '示例设定I']
    for sub in CARD_DIRS:
        d = os.path.join(VAULT, sub)
        if os.path.isdir(d):
            names += [f[:-3] for f in os.listdir(d) if f.endswith('.md')]
    return [n for n in names if len(n) >= 2]


def check(text, grams=None, name_ok=None, deep=False):
    issues = []

    # ①b【低精度候选】人名变体：以本作人名的首字开头、却不属于任何本作人名的 2~3 字串。
    #     能抓到 `示列角色4`，但**误报极多**：人名首字里有「上」「寒」「老」「王」这些常用字，
    #     实测在 16 个真实样本上出了 109 处误报（「上生活」「人生中」「寒不由」…）。
    #     结论：没有语言模型的前提下，"这串字是不是人名"判不准。默认关闭，只在愿意人工筛时开。
    if NAMES and deep:
        firsts = {n[0] for n in NAMES}
        for m in re.finditer('[' + ''.join(sorted(firsts)) + ']', text):
            i = m.start()
            if i + 2 > len(text):
                continue
            win = text[i:i + 3]
            if not re.fullmatch(r'[\u4e00-\u9fff]{2,3}', win):
                continue
            if any(win[:k] in NAMES for k in (3, 2)) or win[:2] in NAMES:
                continue
            ctx = text[max(0, i - 10):i + 14].replace('\n', ' ')
            issues.append(('疑似人名变体/错字', win, ctx))

    # ① 拉丁字母串
    for m in re.finditer(r'[A-Za-z]{2,}', text):
        if any(m.group(0).upper().startswith(x) for x in WHITELIST_ASCII):
            continue
        ctx = text[max(0, m.start() - 12):m.end() + 12].replace('\n', ' ')
        issues.append(('拉丁字母混入', m.group(0), ctx))

    # ①c 异常符号：颜文字、框线符号、几何/杂项符号。
    # 实测抓到过模型在正剧章节里吐出 `(°╯︵┻━┻`（掀桌颜文字）、`♂♂♂♀♀♀`、「你TM怎么…」——
    # 这类混入比错字更显眼，但只查拉丁字母抓不到。
    # ⚠️ 必须用**精确黑名单**（只盯那几个 Unicode 区段），
    #    第一版写成"白名单"（不许出现集合外的任何字符）后，制表符、全角空格全被报出来，
    #    171 处里绝大多数是假阳性，连干净的原文都被报了 71 处。
    for m in ABNORMAL.finditer(text):
        ctx = text[max(0, m.start() - 12):m.end() + 12].replace('\n', ' ')
        issues.append(('异常符号混入（颜文字/特殊字符）', m.group(0), ctx))

    # ② 繁体字
    for m in re.finditer('[' + ''.join(sorted(TRAD_ONLY)) + ']', text):
        ctx = text[max(0, m.start() - 12):m.end() + 12].replace('\n', ' ')
        issues.append(('繁体字混入简体正文', m.group(0), ctx))

    # ③ 日文假名 / 韩文
    for m in re.finditer(r'[\u3040-\u30ff\uac00-\ud7af]+', text):
        ctx = text[max(0, m.start() - 12):m.end() + 12].replace('\n', ' ')
        issues.append(('日韩文字混入', m.group(0), ctx))

    # ④ 同字连续 3 次以上
    for m in re.finditer(r'([\u4e00-\u9fff])\1{2,}', text):
        if m.group(1) in ONOMATOPOEIA:      # 拟声词，正常
            continue
        ctx = text[max(0, m.start() - 12):m.end() + 12].replace('\n', ' ')
        issues.append(('同字连续', m.group(0), ctx))

    # ⑤ 半角标点混入
    for m in HALF_PUNCT.finditer(text):
        ctx = text[max(0, m.start() - 12):m.end() + 12].replace('\n', ' ')
        issues.append(('半角标点混入', m.group(0), ctx))

    # ⑥ 实验性：二字组合未见于源语料（低精度，需人工筛）
    if grams is not None:
        seen = set()
        for seg in re.split(r'[^\u4e00-\u9fff]+', text):
            for i in range(len(seg) - 1):
                g = seg[i:i + 2]
                if g in grams or (name_ok and g in name_ok) or g in seen:
                    continue
                seen.add(g)
                j = text.find(g)
                ctx = text[max(0, j - 14):j + 16].replace('\n', ' ') if j >= 0 else g
                issues.append(('【低精度候选】二字组合未见于源语料', g, ctx))

    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--bigram', action='store_true',
                    help='附带实验性的低精度候选清单（误报多，需人工筛）')
    ap.add_argument('--deep', action='store_true',
                    help='开启深度模式：人名变体 + 二字组合两个低精度信号（需人工筛）')
    a = ap.parse_args()

    grams = name_ok = None
    if a.bigram or a.deep:
        print('正在加载源语料二字组合表（实验性信号）……')
        grams = load_bigrams()
        names = load_user_names()
        name_ok = set()
        for n in names:
            h = re.sub(r'[^\u4e00-\u9fff]', '', n)
            name_ok.update(h[i:i + 2] for i in range(len(h) - 1))
        print(f'  二字组合 {len(grams):,} 个 | 本作专名 {len(names)} 个\n')

    if os.path.isdir(a.path):
        files = [os.path.join(a.path, f) for f in sorted(os.listdir(a.path))
                 if f.endswith('.md')]
    else:
        files = [a.path]

    global NAMES
    # 只用人物卡的名字：物件/设定名常以普通字开头（双、世、桃…），
    # 拿它们做"人名首字"会把「双手抱」这种普通词组误判成人名。
    d = os.path.join(VAULT, '02_人物')
    NAMES = set()
    if os.path.isdir(d):
        NAMES |= {f[:-3] for f in os.listdir(d) if f.endswith('.md')}
    NAMES |= {'主角', '示例角色14', '示例角色12', '示例角色1', '示例角色2', '示例角色7', '示例角色6',
              '示例角色3', '示例角色8', '示例角色11', '示例角色10', '示例角色4', '示例角色9', '示例角色5'}
    if a.deep:
        print(f'本作人名/专名 {len(NAMES)} 个（深度模式的人名变体信号，误报多）')
    print()

    total = collections.Counter()
    clean = 0
    for f in files:
        t = read(f)
        iss = check(t, grams, name_ok, a.deep)
        if not iss:
            clean += 1
            print(f'[干净] {os.path.basename(f)}（{len(t)} 字）')
            continue
        print(f'[{len(iss)} 处] {os.path.basename(f)}（{len(t)} 字）')
        for kind, w, ctx in iss[:15]:
            print(f'   · {kind}：{w}   ← …{ctx}…')
            total[kind] += 1
        if len(iss) > 15:
            print(f'   …… 另有 {len(iss)-15} 处')
        print()

    print('===== 汇总 =====')
    print(f'  干净 {clean} 个 / 共 {len(files)} 个文件')
    for k, v in total.most_common():
        print(f'  {k}: {v} 处')
    if not total:
        print('  未发现字级崩坏。')
    print('\n注：默认只跑高精度信号（拉丁字母/繁体字/日韩文字/同字连续/半角标点），'
          '这几项几乎不误报。')


if __name__ == '__main__':
    main()
