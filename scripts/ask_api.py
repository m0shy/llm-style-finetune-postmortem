# -*- coding: utf-8 -*-
"""极简客户端：把大纲文件发给本地服务，取回正文。

用法:
  python scripts/ask_api.py --outline-file tmp/第1章大纲.txt --chapter 1 --beats 3 --out tmp/第1章.md
  python scripts/ask_api.py --chat "随便问一句"        # 原始模式
"""
import argparse, json, sys, urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

API = 'http://127.0.0.1:8000/v1/chat/completions'


def call(model, content, **kw):
    body = {"model": model, "messages": [{"role": "user", "content": content}],
            "max_new_tokens": kw.pop('max_new_tokens', 1100)}
    body.update(kw)
    req = urllib.request.Request(API, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read().decode('utf-8'))
    return d['choices'][0]['message']['content']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--outline-file')
    ap.add_argument('--chat')
    ap.add_argument('--chapter', default='1')
    ap.add_argument('--beats', type=int, default=3)
    ap.add_argument('--max-new-tokens', type=int, default=1100)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    if a.chat:
        txt = call('自创作品', a.chat, max_new_tokens=400)
        print(txt)
        return

    outline = open(a.outline_file, encoding='utf-8').read().strip()
    print("大纲 %d 字 → 分 %d 幕生成（约 1~3 分钟）..." % (len(outline), a.beats))
    txt = call('自创作品-章节', outline, beats=a.beats, chapter=a.chapter,
               max_new_tokens=a.max_new_tokens)
    print("生成 %d 字 ✓" % len(txt))
    if a.out:
        open(a.out, 'w', encoding='utf-8').write(txt)
        print("已写出", a.out)
    else:
        print(txt)


if __name__ == '__main__':
    main()
