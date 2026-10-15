# -*- coding: utf-8 -*-
"""扫描训练语料里的盗版网站广告 / 站点水印残留。

起因：2026-09-18 GGUF 版生成时吐出
  「名（<站点域名>）。笔趣阁手机版更新最快！手机用户可访问 <站点域名>」
→ 说明语料里有广告行没清掉 ✗
"""
import json, re, collections, sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

PATS = {
    '网址': re.compile(r'[A-Za-z0-9\-]{3,}\.(?:com|net|org|cc|cn|xyz|top|vip|info|me|la)\b'),
    '笔趣阁': re.compile(r'笔趣阁'),
    '手机版': re.compile(r'手机版'),
    '更新最快': re.compile(r'更新最快'),
    '手机用户': re.compile(r'手机用户'),
    '记住本站': re.compile(r'记住本站|记住域名|收藏本站|请记住'),
    '求票求推荐': re.compile(r'求月票|求推荐票|求收藏|求订阅'),
    '无弹窗': re.compile(r'无弹窗|全文阅读|免费阅读|首发'),
    '章节报错': re.compile(r'章节报错|内容报错|举报'),
}

FILES = [
    (r'<项目目录>\LLaMA-Factory\data\cpt_corpus_v2.jsonl', 'text', 'CPT 语料'),
    (r'<项目目录>\LLaMA-Factory\data\dataset_multi_v25_flat2.jsonl', 'output', 'SFT 数据'),
]


def main():
    hits = collections.Counter()
    examples = {}
    for path, field, label in FILES:
        n = bad = 0
        for line in open(path, encoding='utf-8'):
            if not line.strip():
                continue
            n += 1
            t = json.loads(line).get(field, '')
            hit = False
            for k, rx in PATS.items():
                m = rx.search(t)
                if m:
                    hits[k] += 1
                    hit = True
                    if k not in examples:
                        s = max(0, m.start() - 35)
                        examples[k] = (label, t[s:m.end() + 35].replace('\n', '|'))
            if hit:
                bad += 1
        pct = 100 * bad / max(1, n)
        flag = '✗' if pct > 1 else '✓'
        print('  %s %-10s %5d 条 → 有残留 %d 条 (%.2f%%)' % (flag, label, n, bad, pct))
    print()
    print('  按类型：')
    for k, c in hits.most_common():
        print('    %-12s %5d 次' % (k, c))
        if k in examples:
            lab, ex = examples[k]
            print('        例（%s）: %s' % (lab, ex[:120]))


if __name__ == '__main__':
    main()
