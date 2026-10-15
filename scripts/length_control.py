# -*- coding: utf-8 -*-
"""长度控制器 v1（2026-09-20）：max_tokens 硬限 + 句尾修剪。

背景（实测诊断 ✓）：
  模型的"软停止"不可靠 ✗ —— 无论温度高低，都会写到 max_tokens 顶满 ✗
  → 训练的"目标字数→停止"映射没学牢 ✗（EOS 信号弱 ✗）
工程解法（可靠 ✓）：
  ① max_tokens = 目标字数 ÷ 1.6（中文字符/token 实测比 ✓）+ 5% 余量
  ② 句尾修剪：截断处若在句中 → 回退到最近的句末标点 ✓
  ③ 广告过滤 ✓
"""
import json
import re
import urllib.request

API = 'http://127.0.0.1:8001/v1/chat/completions'
NAMES = open(r'<项目目录>\Datasets\names\自创作品_专名.txt', encoding='utf-8').read().strip()

_s = open(r'<项目目录>\Datasets\scripts\serve_chapter_api.py', encoding='utf-8').read()
_i = _s.find('INSTRUCTION = """') + len('INSTRUCTION = """')
_j = _s.find('"""', _i)
INSTR = _s[_i:_j]

_AD = re.compile(r'(请记住本书|首发域名|更新最快|手机版更新|手机用户请浏览|笔趣阁|无弹窗|'
                 r'[A-Za-z0-9\-]{3,}\.(?:com|net|org|cc|cn|xyz|top|vip|la|me)\b)')
_句末 = re.compile(r'[。！？”]$')


def 句尾修剪(text):
    """截断的最后一句若不完整 → 回退到最近的句末标点 ✓"""
    t = text.rstrip()
    if _句末.search(t[-3:]):
        return t
    # 找最后一个句末标点
    best = -1
    for m in re.finditer(r'[。！？”]', t):
        best = m.end()
    if best > 0:
        return t[:best]
    return t


def 生成控长(大纲, 目标字数, 温度=0.8):
    """按目标字数生成正文 ✓（硬限 + 修剪 ✓）"""
    maxtok = int(目标字数 / 1.6 * 1.05) + 8
    instr = INSTR + ('\n\n【本次要求】把上面的大纲扩写成一段连贯正文。'
                     f'**目标长度约 {目标字数} 字**。'
                     '写到自然段落结束即可。')
    inp = NAMES + '\n\n==== 本次要写 ====\n章级大纲：' + 大纲 + '\n'
    body = {'model': '自创作品',
            'messages': [{'role': 'user', 'content': instr + '\n\n' + inp}],
            'max_tokens': maxtok, 'temperature': 温度, 'top_p': 0.9,
            'repeat_penalty': 1.15}
    req = urllib.request.Request(API, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=1200) as r:
        d = json.loads(r.read().decode('utf-8'))
    raw = d['choices'][0]['message']['content']
    raw = 句尾修剪(_AD.sub('', raw))
    return raw, d['usage']['completion_tokens']


if __name__ == '__main__':
    import sys
    大纲 = '主角买生日蛋糕，目击红裙女人碎成光粒，去抓落空，周围人无反应，他怀疑幻觉。'
    print('=== 控长实测（目标 300 字 ✓）===')
    t, nt = 生成控长(大纲, 300)
    dev = 100 * (len(t) - 300) / 300
    print('  实际 %d 字（偏差 %+.0f%%）%s' % (
        len(t), dev, '✅' if abs(dev) <= 20 else '⚠️'))
    print('  尾部:', t[-50:].replace('\n', ' '))
    print()
    print('=== 控长实测（目标 800 字 ✓）===')
    o8 = ('主角给三妹买生日蛋糕，目击红裙女人碎成光粒，去抓落空，周围人无反应。'
          '他查监控、问路人确认是否幻觉，回到家发现小卖部变成面馆，老板坚称十年没换过招牌。')
    t2, nt2 = 生成控长(o8, 800)
    dev2 = 100 * (len(t2) - 800) / 800
    print('  实际 %d 字（偏差 %+.0f%%）%s' % (
        len(t2), dev2, '✅' if abs(dev2) <= 20 else '⚠️'))
    print('  尾部:', t2[-50:].replace('\n', ' '))
