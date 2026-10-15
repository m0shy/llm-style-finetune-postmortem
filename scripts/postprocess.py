# -*- coding: utf-8 -*-
"""生成结果的统一后处理：剥标题头 + 过滤语料里的盗版站广告。

两个问题都是实测出来的：
  ① 模型爱在正文前加「【第1章】」「【正文·765字】【02:43】」「第一章：面馆与"白瓶"」
     —— 训练要求是"只输出正文"，但它偶尔不听话 ✗ → 后处理兜底 ✓
  ② 语料里混着盗版站水印（CPT 57 条 / SFT 4 条 ✗），模型学会了会吐出来 ✗

用法：
    from postprocess import 清洗
    text = 清洗(raw)
"""
import re

# ---------------- ① 广告过滤 ----------------
_广告 = re.compile(
    r'(请记住本书|记住本书首发|首发域名|更新最快网址|手机版更新|手机用户请浏览|'
    r'笔趣阁|无弹窗|免费阅读|全文阅读|请记住本站|章节内容不完整|'
    r'[A-Za-z0-9\-]{3,}\.(?:com|net|org|cc|cn|xyz|top|vip|la|me)\b)')


def 过滤广告(text):
    """整行命中且该行不长 → 删整行；长行里夹着 → 挖掉片段"""
    out = []
    for ln in text.split('\n'):
        if _广告.search(ln) and (len(ln) < 90 or len(re.findall(r'。', ln)) <= 2):
            continue
        out.append(_广告.sub('', ln))
    return '\n'.join(out)


# ---------------- ② 剥标题头/尾 ----------------
_标题模式 = [
    re.compile(r'^【[^】]{0,30}】$'),                       # 【第1章】
    re.compile(r'^(【[^】]{0,26}】\s*){1,4}$'),              # 连着的 1~4 个方括号块
    re.compile(r'^第\s*[0-9一二三四五六七八九十百]+\s*章[\s:：、·\-—]{0,4}.*$'),  # 第一章：xxx
    re.compile(r'^\[?\s*[0-9]{1,2}\s*[:：]\s*[0-9]{2}\s*\]?$'),          # [02:43]
    re.compile(r'^[（(【\[]?\s*(正文|字数|本文|全文字数)\s*[）)】\]]?\s*[:：·]?\s*[0-9]+\s*字?\s*$'),
    re.compile(r'^[·\-—=*]{3,}$'),                                     # 分隔线
]

# 纯标题行特征：短、无句末标点、不以下引号/对话开头
_句末 = re.compile(r'[。！？…]')


def _是标题行(line):
    s = line.strip()
    if not s or len(s) > 42:          # 太长就不是标题
        return False
    if any(p.match(s) for p in _标题模式):
        return True
    # 兜底：很短、不含句末标点、不以引号或对话标记开头 → 判断为标题
    if len(s) <= 22 and not _句末.search(s) and not s.startswith(('“', '"', '「', '（', '(')):
        # 且不像正文开头（正文常见以人名/代词+动作起手）
        return True
    return False



def 剥标题(text):
    lines = text.split('\n')
    # 从前往后剥（最多 5 行，防止误删正文）
    head = 0
    while head < len(lines) and head < 5 and (not lines[head].strip() or _是标题行(lines[head])):
        head += 1
    # 从后往前剥
    tail = len(lines)
    while tail > head and tail > len(lines) - 4 and (not lines[tail - 1].strip() or _是标题行(lines[tail - 1])):
        tail -= 1
    return '\n'.join(lines[head:tail]).strip()


def 清洗(text):
    """完整后处理：先剥头尾，再滤广告"""
    return 过滤广告(剥标题(text)).strip()


if __name__ == '__main__':
    import sys, os
    files = sys.argv[1:] or [
        r'<项目目录>\Datasets\tmp\第1章_混合版.md',
        r'<项目目录>\Datasets\tmp\第1章_GGUF版.md',
        r'<项目目录>\Datasets\tmp\_test_chapter.md',
    ]
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    for f in files:
        if not os.path.exists(f):
            continue
        raw = open(f, encoding='utf-8').read()
        clean = 清洗(raw)
        print('=' * 62)
        print('  %s' % os.path.basename(f))
        print('  %d 字 → %d 字' % (len(raw), len(clean)))
        print('  原始开头: %s' % raw[:60].replace('\n', ' | '))
        print('  清洗开头: %s' % clean[:60].replace('\n', ' | '))
        print('  残留广告: %s' % ('有 ✗' if _广告.search(clean) else '无 ✓'))
