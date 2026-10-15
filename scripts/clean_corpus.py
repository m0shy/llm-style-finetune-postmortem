# -*- coding: utf-8 -*-
"""深度语料清洗器：把网文 txt 洗成纯正文。

清除类型（全部实测遇到）：
  ① 盗版站广告（笔趣阁/首发域名/更新最快/手机版/无弹窗/网址/起点番茄引流…）
  ② 作者的话 / 本章说 / 上架感言 / 感言 / PS:附注
  ③ 请假条 / 断更说明 / 停更欠更补更
  ④ 求月票 / 求推荐票 / 求收藏 / 求订阅 / 求鲜花 / 求评价票
  ⑤ 读者打赏感谢 / 盟主堂主舵主 / 书友
  ⑥ （本章完）（未完待续）等章节尾巴
  ⑦ 新书旧书推广 / 其他站点引流
  ⑧ [图片][附件] 占位符

原则：
  · 行级判断：整行命中才删整行；长行里夹片段 → 只挖片段
  · 保守：绝不删带句号的普通正文行 ✗
  · 全程统计：每本书删了多少行、按类别各多少 → 输出报告

用法：
  python clean_corpus.py 输入1.txt 输入2.txt ... --outdir 输出目录
"""
import re
import os
import sys
import collections

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ---------------- 类别表（统计用） ----------------
_CATS = [
    ('盗版站广告', r'(笔趣阁|首发域名|更新最快网址|手机版更新最快|手机用户请浏览|无弹窗|免费阅读|全文阅读|请记住本书|请记住本站|本书最新章节|一秒记住|天才一秒记住|本站网址|最新章节网址)'),
    ('网址', r'[A-Za-z0-9\-]{2,}\.(?:com|net|org|cc|cn|xyz|top|vip|la|me|info|bid|club|website)'),
    ('站点引流', r'(起点中文|纵横中文|飞卢小说网|番茄小说|七猫|晋江文学城|17k|掌阅|书旗|爱国{0,2}者中文网)'),
    ('作者的话', r'^(作者的话|本章说|上架感言|感言|作者留言|作者的话[:：]|PS[:：.]|ps[:：.])'),
    ('上架相关', r'(上架了|今天上架|明天上架|首订|均订|裸奔求)'),
    ('请假断更', r'(请假条|断更一天|断更通知|今天断更|停更|欠更|补更|请假.*更新|抱歉.*断更)'),
    ('求票求支持', r'(求月票|求推荐票|求收藏|求订阅|求鲜花|求评价票|求打赏|求一切|投月票|投推荐票)'),
    ('打赏感谢', r'(感谢.{0,16}(打赏|盟主|舵主)|打赏.{0,8}(起点币|阅点)|书友[0-9]{5,})'),
    ('章节尾巴', r'^[（(【]?\s*(本章完|未完待续|求收藏|求订阅|本章结束|正文完?)\s*[）)】]?\.?$'),
    ('新书推广', r'(新书.{0,10}(求支持|已发布|上线)|另一本书|我的新书|完结老书)'),
    ('占位符', r'^\s*[［\[](图片|附件|语音|视频)[］\]]\s*$'),
]

DEL_LINE = [re.compile(rx) for _, rx in _CATS]

STRIP_FRAG = [
    re.compile(r'[A-Za-z0-9\-]{2,}\.(?:com|net|org|cc|cn|xyz|top|vip|la|me|info|bid|club)[/\w\-.]*', re.I),
    re.compile(r'(笔趣阁|首发域名|更新最快|手机版更新|手机用户请浏览|无弹窗|免费阅读|全文阅读|请记住本书|请记住本站)'),
    re.compile(r'(求月票|求推荐票|求收藏|求订阅|求鲜花|求评价票|求打赏)'),
    re.compile(r'[（(【]?\s*(?:本章完|未完待续)\s*[）)】]?'),
]

_句末 = re.compile(r'[。！？…”』」]')


def _read(path):
    raw = open(path, 'rb').read()
    for enc in ('utf-8', 'gb18030', 'gbk', 'utf-16'):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode('utf-8', errors='replace')


def _classify(s):
    for name, rx in _CATS:
        if re.search(rx, s):
            return name
    return '其他'


def _verdict(s):
    """返回 ('删', 类别) / ('挖', '') / ('留', '')"""
    # 铁模式：无论如何都删（明确的站点水印/网址/占位符 ✓）
    for rx in (DEL_LINE[0], DEL_LINE[1], DEL_LINE[2], DEL_LINE[9], DEL_LINE[10]):
        if rx.search(s):
            return ('删', _classify(s))
    # 软模式：只有"短行 + 无句末标点"才删（标题/作者话/求票 ✓）
    soft_hit = None
    for idx, rx in enumerate(DEL_LINE):
        if idx in (0, 1, 2, 9, 10):
            continue
        if rx.search(s):
            soft_hit = idx
            break
    if soft_hit is not None:
        if len(s) < 60 and not _句末.search(s):
            return ('删', _classify(s))
        # 长行或带句末 → 只挖片段（保守 ✓）
        return ('挖', '')
    return ('留', '')


def clean_text(text, stats):
    """清洗一本书的全部文本，返回 (正文, 统计 Counter)。"""
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            out.append('')
            continue
        verdict, cat = _verdict(s)
        if verdict == '删':
            stats[('删行', cat)] += 1
            continue
        s2 = s
        for rx in STRIP_FRAG:
            s2 = rx.sub('', s2)
        if s2 != s:
            stats[('挖片段', '')] += 1
        if s2.strip():
            out.append(s2)
        else:
            stats[('挖空', '')] += 1
    merged, blank = [], 0
    for ln in out:
        if not ln:
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        merged.append(ln)
    return '\n'.join(merged).strip(), stats


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    outdir = r'<项目目录>\Datasets\语料_清洗后'
    os.makedirs(outdir, exist_ok=True)
    if not args:
        print('用法: python clean_corpus.py 书1.txt 书2.txt ...')
        print('清洗结果写入:', outdir)
        sys.exit(1)

    grand = collections.Counter()
    for path in args:
        if not os.path.isfile(path):
            print('  ✗ 不存在:', path)
            continue
        name = os.path.basename(path)
        text = _read(path)
        stats = collections.Counter()
        cleaned, stats = clean_text(text, stats)
        dst = os.path.join(outdir, 'clean_' + name)
        open(dst, 'w', encoding='utf-8').write(cleaned)
        print('=' * 66)
        print('  %s' % name)
        print('  %d 字 → %d 字（删 %d 字，%.1f%%）' % (
            len(text), len(cleaned), len(text) - len(cleaned),
            100 * (len(text) - len(cleaned)) / max(1, len(text))))
        for (act, cat), n in sorted(stats.items(), key=lambda x: -x[1]):
            if act == '删行':
                print('    删行 %-8s %5d 行' % (cat or '', n))
        if ('挖片段', '') in stats:
            print('    挖除片段 %6d 处' % stats[('挖片段', '')])
        print('  已写出:', dst)
        grand.update(stats)
    print('=' * 66)
    print('【全部合计】')
    for (act, cat), n in sorted(grand.items(), key=lambda x: -x[1]):
        if act == '删行':
            print('  删行 %-8s %5d 行' % (cat or '', n))
    if ('挖片段', '') in grand:
        print('  挖除片段 %6d 处' % grand[('挖片段', '')])


if __name__ == '__main__':
    main()
