# -*- coding: utf-8 -*-
"""用 llama-server 跑章节生成（带完整规则 + 专名块，格式与训练一致）。

对比目标：同一个大纲，bnb 版崩了 5 次 ✗，看 GGUF 版能不能稳定产出。
"""
import json, sys, time, urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

API = 'http://127.0.0.1:8001/v1/chat/completions'

# 🔴 统一后处理（剥标题头 + 过滤盗版站广告）
#    两个问题都是实测出来的，见 scripts/postprocess.py 的注释 ✓
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from postprocess import 清洗 as 后处理, 过滤广告 as _过滤广告

# ⚠️ 2026-09-19：上一次编辑误删了下面三个常量 ✗（"改完必核"又栽了一次）
#    这次补回来并加护栏 ✓
_API_SRC = r'<项目目录>\Datasets\scripts\serve_chapter_api.py'
_s = open(_API_SRC, encoding='utf-8').read()
_i = _s.find('INSTRUCTION = """') + len('INSTRUCTION = """')
_j = _s.find('"""', _i)
assert _i > 20 and _j > _i, '从 serve_chapter_api.py 里取不到写作规则 ✗'
INSTRUCTION = _s[_i:_j]

NAMES_PATH = r'<项目目录>\Datasets\names\自创作品_专名.txt'
assert _os.path.isfile(NAMES_PATH), f'专名文件不存在: {NAMES_PATH} ✗'
NAMES = open(NAMES_PATH, encoding='utf-8').read().strip()

BOOK = "自创作品"


def split_beats(text, n):
    import re
    paras = [p.strip() for p in re.split(r'\n\s*\n|\n', text) if p.strip()]
    if len(paras) >= n:
        size = (len(paras) + n - 1) // n
        return [''.join(paras[i:i + size]) for i in range(0, len(paras), size)][:n]
    import re as _re
    sents = [s.strip() for s in _re.split(r'(?<=[。！？；])', text) if s.strip()]
    if not sents:
        return [text.strip()] * n
    size = (len(sents) + n - 1) // n
    return [''.join(sents[i:i + size]) for i in range(0, len(sents), size)][:n]


def call(prompt, maxtok, temp=0.8, topp=0.9):
    body = {"model": "自创作品", "messages": [{"role": "user", "content": prompt}],
            "max_tokens": maxtok, "temperature": temp, "top_p": topp,
            "repeat_penalty": 1.15, "cache_prompt": False}
    req = urllib.request.Request(API, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=1800) as r:
        d = json.loads(r.read().decode('utf-8'))
    return d['choices'][0]['message']['content'], d.get('timings', {})


if __name__ == '__main__':
    outline = open(sys.argv[1], encoding='utf-8').read().strip()
    beats = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    maxtok = int(sys.argv[3]) if len(sys.argv) > 3 else 1100
    out = sys.argv[4] if len(sys.argv) > 4 else r'<项目目录>\Datasets\tmp\gguf_ch1.md'

    bs = split_beats(outline, beats)
    print("大纲 %d 字 → 分 %d 幕 | 每幕上限 %d token" % (len(outline), len(bs), maxtok))
    segs, total_tokens, total_sec = [], 0, 0.0
    for i, b in enumerate(bs, 1):
        inp = (NAMES + "\n\n==== 本次要写 ====\n"
               + f"《{BOOK}》第1章（本次只写这一幕的第 {i}/{len(bs)} 段，不要写完整章）\n"
               + f"章级大纲：{b}\n本章爽点闭环：（见章级大纲）\n")
        t0 = time.time()
        try:
            txt, tim = call(INSTRUCTION + "\n\n" + inp, maxtok)
        except Exception as e:
            print("  ✗ 第 %d 幕失败: %s" % (i, e)); break
        dt = time.time() - t0
        total_tokens += tim.get('predicted_n', 0)
        total_sec += dt
        print("  第 %d/%d 幕: %d 字 | %.0f 秒 | %.1f token/s ✓" % (
            i, len(bs), len(txt), dt, tim.get('predicted_per_second', 0)))
        segs.append(txt)

    chapter = '\n\n'.join(segs)
    # 推理侧广告过滤 ✓（语料污染兜底）
    before = len(chapter)
    chapter = 后处理(chapter)
    if before != len(chapter):
        print("  ⚠️ 过滤掉 %d 字的语料残留广告 ✓" % (before - len(chapter)))
    open(out, 'w', encoding='utf-8').write(chapter)
    print("=" * 60)
    print("完成: %d 字（%d 幕）| 总 %d token / %.0f 秒 | 均速 %.1f token/s" % (
        len(chapter), len(segs), total_tokens, total_sec,
        total_tokens / total_sec if total_sec else 0))
    print("已写出:", out)
