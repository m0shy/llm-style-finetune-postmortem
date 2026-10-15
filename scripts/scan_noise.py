# -*- coding: utf-8 -*-
"""作者话 / 平台广告 / 请假条 等"非正文"污染扫描与清理

为什么要单独做：CPT 学的是**语言分布**，作者话混进去 = 教模型写作者话。
而现有的 CPT 语料构建脚本（build_cpt_corpus.py）只去了「章标题行 + 空行」，
**没有过滤作者话** —— 这是个真实的风险，必须先查。

污染类型：
  A 作者话    码字/加更/断更/请假/上架感言/完结感言/作者的话/今天两更…
  B 运营话    求月票/求推荐票/求收藏/求订阅/打赏/首订/均订/追读…
  C 读者互动  读者/书友/大佬/兄弟姐妹/本章说/评论区/感谢…
  D 平台残留  本章未完请点击下一页/起点中文网/阅文/qidian/www./手机版阅读网址…
  E 分页水印  本章未完/未完待续/【未完待续】/（本章完）…

用法：
  python scripts/scan_noise.py "文件或目录"              # 只扫描，报告
  python scripts/scan_noise.py "文件或目录" --clean      # 输出清理后的文件
  python scripts/scan_noise.py --check-corpus            # 反查已有训练集
"""
import os, re, sys, glob, argparse, json

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ── 污染模式 ────────────────────────────────────────────────
# ⚠️ 分两层：HI 层是**高精度**标记（几乎不可能出现在正文里）→ 直接删；
#    LO 层是**需要看上下文**的（"大佬/订阅/留言/打赏"在剧情里完全正常，
#    比如灵境里就有直播间打赏的桥段）→ 只报告不自动删。
#    第一版把两层混在一起，假阳性一堆（"身体不太协调"命中"身体不"、"作息时间"命中"作息"），
#    所以拆开并各自做过正反例验证。
HI = re.compile(
    # —— 作者话（高精度）——
    r'(^|\s)(ps|PS|Ps)[：:].{0,80}$'   # ps：——实测 587 行真污染
    r'|作者的话|作者有话说|上架感言|完结感言|新书感言|完本感言'
    r'|今天请假|请假一天|明天恢复更新|恢复更'   # 去掉裸'请假条'（剧情里可以是道具，如'拿出那把请假条'）
    r'|求月票|求推荐票|求收藏|求订阅|求追读|求打赏'
    r'|月票加更|加更一章|加更规则|加更还债'
    r'|均订|首订|订阅量|追读量|三江推荐|(?<!强行)强推'
    # ⚠️ 子串跨词误匹配：'判断更加精准' → 判**断更**加，被当成作者话 ✗
    #    实测就是这么漏进来 1 行的。凡短词都要防跨词。
    r'|码字|卡文了|(?<![判])断更|写不出来|没有灵感'
    # —— 平台/盗版站残留 ——
    r'|本章未完|请点击下一页|【未完待续】|^未完待续$|（本章完）|\(本章完\)'   # 未完待续要独立成行（'直播到一半未完待续的感觉'是正文）
    r'|起点中文网|起点女生网|阅文集团|qidian|创世中文网'
    r'|手机阅读|手机版阅读|阅读网址|免费阅读|无广告'
    r'|https?://|www\.|m\./novel|book\.qidian|book\.zongheng'
    r'|\.com|\.org|\.net'
    r'| sud u|sudugu|biquge|biqukan|xbique'
    # —— 分隔线 / 空水印 ——
    r'|^[\s]*[-=*_]{4,}[\s]*$'
    # —— 盗版站/转载水印（2026-09-15 从文件头实测补上）——
    # 盗版站水印：**用通用模式**，不要逐个站名列举（新书又会换一家）
    r'|来源[：:]\s*\S*(网|站|谷|阁|堂|屋|居|轩|斋|小说)'
    r'|速读谷|sudugu|得奇小说网|deqixs|笔趣阁|biquge'
    r'|^\s*书名[：:]|^\s*简介[：:]|^\s*作者[：:]'
    r'|^\s*《.{2,20}》\s+作者[：:]'      # 《书名》  作者：某某
    r'|^\s*章节范围[：:]'
    r'|^\s*网址[：:]\s*https?'
    r'|^\s*(正文卷|第一卷：默认|第二卷|第三卷|第四卷|第五卷|VIP卷|作品相关|作者相关)\s*$'
)
# LO 层：只统计报告，不自动删（这些在剧情里大量合法出现）
LO = re.compile(
    r'(读者|书友|大佬|兄弟们|家人们|老铁|各位看官|本章说|评论区|书评区'
    r'|推荐票|月票|打赏|订阅|收藏|盟主|舵主|堂主|首订|追更)')

# ── 内容级检测（行级模式抓不到的）─────────────────────────────
# ① 属性数据块：惊悚乐园开篇整章是"物品数据库"，全是【名称：xx】【类型：xx】。
#    这类块不是叙事，混进去 = 教模型写道具属性表 ✗
STAT_BLOCK = re.compile(r'【[^】]{1,10}[：:][^】]{0,40}】')
# ② 动漫同人内容：无限流会进入火影/海贼等世界，出现动漫角色名。
#    用户作品是原创都市，这些外来专名会把语域带偏 ✗
#    ⚠️ 2026-09-15 修正：第一版把「高达/木叶/草帽/龙珠」也放进来了 ——
#    但"高达"在中文里是常用词（"价格高达"，实测假阳性一堆），"草帽/木叶"也可能是字面意思 ✗。
#    现在只留**几乎不可能出现在原创都市文里**的专名。
ANIME_NAMES = re.compile(
    r'(宇智波|带土|佐助|鸣人|卡卡西|我爱罗|查克拉|写轮眼|千手柱间|自来也|大蛇丸|'
    r'路飞|索隆|娜美|乔巴|恶魔果实|'
    r'灰原哀|江户川|'
    r'贝吉塔|赛亚人|弗利萨|'
    r'初号机|使徒来袭|'
    r'蜘蛛侠|钢铁侠|灭霸|'
    r'霍格沃茨|伏地魔)')

def is_stat_block(text, min_hits=5, per_1k=4.0):
    """整块文本是否以属性数据为主（【名称：…】【类型：…】这类）。
    惊悚乐园开篇整章是"物品数据库"，不是叙事 —— 混进去会教模型写道具属性表 ✗。"""
    n = len(text)
    if n < 300:
        return False
    hits = len(STAT_BLOCK.findall(text))
    return hits >= min_hits and hits / n * 1000 >= per_1k


def has_anime(text, min_hits=2):
    return len(ANIME_NAMES.findall(text)) >= min_hits


# ps：开头的行**不受长度保护** —— 实测有一条 "ps：写的比较慢，感觉比装逼打…" 超过 140 字，
# 被长度守卫放过了 ✗。而 "ps：" 开头几乎必然是作者话，没有正文会长这样。
PS_LINE = re.compile(r'^\s*(ps|PS|Ps)[：:]')
PATTERNS = {'HI 高精度（可直接删）': HI, 'LO 低精度（仅报告）': LO}


def read_text(path):
    """稳健读取中文小说 txt。

    ⚠️ 必须用**严格解码 + 合理性检查**，不能用 errors='ignore'。
    2026-09-15 踩的大坑：原写法
        open(p, encoding='utf-8', errors='ignore')
    对 GBK 文件**永远不会报错**（非法字节被静默丢弃），于是 GBK 回退分支永远走不到，
    结果 4 本 GBK 编码的书（超神机械师/轮回乐园/惊悚乐园/这游戏也太真实了）
    在语料里 98% 是乱码 —— 实测解析出的汉字数相差 44~68 倍。
    """
    raw = open(path, 'rb').read()
    for enc in ('utf-8', 'gb18030', 'utf-16'):
        try:
            t = raw.decode(enc)            # 严格解码：失败会抛异常
        except Exception:
            continue
        head = t[:20000]
        cn = sum(1 for c in head if '\u4e00' <= c <= '\u9fff')
        # 合理性检查：前 2 万字里中文应超过 500 个（纯英文/代码文件除外）
        if cn > 500 or len(t) < 3000:
            return t
    return raw.decode('utf-8', errors='ignore')


def read_any(p):
    if os.path.isdir(p):
        return ''.join(read_any(f) for f in sorted(glob.glob(os.path.join(p, '**', '*.txt'), recursive=True)))
    return read_text(p)


def scan_text(t, per_line=True, sample=3):
    """返回 {类别: (命中次数, [样例])}"""
    res = {}
    lines = t.split('\n')
    for name, pat in PATTERNS.items():
        hits = []
        cnt = 0
        for ln in lines:
            if pat.search(ln):
                cnt += 1
                if len(hits) < sample:
                    hits.append(ln.strip()[:70])
        if cnt:
            res[name] = (cnt, hits)
    return res


def clean_lines(t, aggressive=True):
    """按行清理。返回 (清后文本, 删除行数)"""
    keep, drop = [], 0
    for ln in t.split('\n'):
        s = ln.strip()
        if not s:
            keep.append(ln); continue
        bad = any(p.search(s) for p in PATTERNS.values())
        # 只删"短行"里的污染（长正文段落里出现"读者"是正常的）
        if bad and (aggressive or len(s) <= 80):
            if len(s) <= 120:          # 作者话一般不会太长
                drop += 1
                continue
        keep.append(ln)
    return '\n'.join(keep), drop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', nargs='?')
    ap.add_argument('--clean', action='store_true', help='输出清理后的文件')
    ap.add_argument('--check-corpus', action='store_true', help='反查已有训练集')
    a = ap.parse_args()

    if a.check_corpus:
        targets = [
            (r'<项目目录>\Datasets\cpt_corpus.jsonl', 'CPT 语料（当前 cpt_v1 用的）'),
            (r'<项目目录>\LLaMA-Factory\data\dataset_multi_v23.jsonl', 'SFT 数据 multi_v23'),
        ]
        print('===== 反查已有训练集 =====\n')
        for path, label in targets:
            if not os.path.isfile(path):
                print(f'  {label}: 找不到 {path}'); continue
            t = read_text(path)   # 2026-09-16：自己也犯了同一个错，改用统一读取
            # jsonl 里带转义，先反转义再扫
            t = t.replace('\\n', '\n').replace('\\"', '"')
            res = scan_text(t)
            total = sum(v[0] for v in res.values())
            print(f'  【{label}】  {total} 行命中')
            for k, (c, s) in sorted(res.items(), key=lambda x: -x[1][0]):
                print(f'    {k:<12} {c:>6} 行')
                for x in s:
                    print(f'        例: {x}')
            print()
        return

    t = read_any(a.path)
    if not t:
        print(f'读不到：{a.path}'); return
    res = scan_text(t, sample=5)
    total = sum(v[0] for v in res.values())
    print(f'===== 污染扫描：{os.path.basename(a.path)} =====')
    print(f'总字数 {len(t):,} | 命中行 {total}\n')
    for k, (c, s) in sorted(res.items(), key=lambda x: -x[1][0]):
        print(f'  {k:<12} {c:>6} 行')
        for x in s:
            print(f'        {x}')
    if a.clean:
        t2, drop = clean_lines(t)
        out = a.path.rsplit('.', 1)[0] + '_clean.txt'
        open(out, 'w', encoding='utf-8').write(t2)
        print(f'\n已清理：删 {drop} 行，{len(t):,} → {len(t2):,} 字')
        print(f'输出：{out}')


if __name__ == '__main__':
    main()
