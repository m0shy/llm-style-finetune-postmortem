# -*- coding: utf-8 -*-
"""长度可控验收 v2（2026-09-20）：提示与训练分布严格对齐 ✓

v1 教训：① instruction 与训练不一致 ✗ ② 三档共用同一份 130 字大纲 ✗
        模型学到的是「大纲长度↔输出长度」强相关 ✗ → 大纲 130 字时三档都输出 ~1500 字 ✗
v2 修正：instruction = 训练同源完整规则 ✓ + 大纲长度按训练各档分布对齐 ✓
"""
import json, os, re, sys, urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

API = 'http://127.0.0.1:8001/v1/chat/completions'
NAMES = open(r'<项目目录>\Datasets\names\自创作品_专名.txt', encoding='utf-8').read().strip()

# 训练同源规则 ✓（与 build_sft_lenctl.py 完全一致 ✓）
_s = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serve_chapter_api.py'), encoding='utf-8').read()
_i = _s.find('INSTRUCTION = """') + len('INSTRUCTION = """')
_j = _s.find('"""', _i)
INSTR = re.sub(r'【输出】[^\n]*',
               '【输出】只输出正文。**绝对不要输出标题、章节号、字数统计、时间戳、分隔线或任何标记**，直接以下一个自然段开始。',
               _s[_i:_j])

# 大纲按训练各档分布对齐：300 档练的是 ~55 字大纲 ✓ 800 档 ~150 ✓ 1500 档 ~300 ✓
TIERS = [
    (300, 55, '主角买生日蛋糕，目击红裙女人碎成光粒，去抓落空，周围人无反应，他怀疑幻觉。'),
    (800, 150, '主角给三妹买生日蛋糕，路过便利店时目击红裙女人碎成光粒。他本能去抓落空，周围人毫无反应。'
              '他第一反应是查手机监控、问路人，确认是否幻觉。回到家发现常去的小卖部变成了面馆，老板说十年没换过招牌。'),
    (1500, 300, '主角给三妹买生日蛋糕，路过便利店目击红裙女人碎成光粒。他本能去抓落空，周围人毫无反应，'
               '他第一反应不是喊叫而是查监控、问路人确认是否幻觉。回到家发现小卖部变成面馆，老板坚称十年没换招牌。'
               '母亲打电话提醒晚上给小爹祝寿，主角心不在焉地应答。挂断后他盯着面馆招牌，发现招牌细节与记忆完全对不上，'
               '记忆和现实出现了裂缝。'),
]

AD = re.compile(r'(请记住本书|首发域名|更新最快|笔趣阁|无弹窗|'
                r'[A-Za-z0-9\-]{3,}\.(?:com|net|org|cc|cn|xyz|top|vip|la|me)\b)')
POLLUTION = ['许七安','张元清','苏沐橙','陈歌','李昂','张雅','苏钰','李东泽','傅青阳','赵城隍','关雅']


def call(goal, outline):
    instr = INSTR + (
        '\n\n【本次要求】把上面的大纲扩写成一段连贯正文。'
        f'**目标长度约 {goal} 字**（允许上下浮动一成半）。'
        '宁可在细节上多铺陈，也不要提前收尾。')
    inp = NAMES + '\n\n==== 本次要写 ====\n' + f'章级大纲（{len(outline)} 字）：{outline}\n本章爽点闭环：（见章级大纲）\n'
    body = {'model': '自创作品', 'messages': [{'role': 'user', 'content': instr + '\n\n' + inp}],
            'max_tokens': int(goal * 1.7), 'temperature': 0.8, 'top_p': 0.9, 'repeat_penalty': 1.15}
    req = urllib.request.Request(API, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=1800) as r:
        d = json.loads(r.read().decode('utf-8'))
    return d['choices'][0]['message']['content']


def main():
    print('=' * 64)
    print('长度可控验收 v2（提示与训练分布对齐 ✓）')
    print('=' * 64)
    all_ok = True
    for goal, olen, outline in TIERS:
        print('\n【目标 %d 字 · 大纲 %d 字 ✓】生成中…' % (goal, len(outline)))
        t = call(goal, outline)
        n = len(t)
        dev = 100 * (n - goal) / goal
        ok = abs(dev) <= 45
        bad = [x for x in POLLUTION if x in t]
        ad = bool(AD.search(t))
        if not ok or bad or ad:
            all_ok = False
        print('  实际 %d 字（偏差 %+.0f%%）%s | 污染:%s | 广告:%s' % (
            n, dev, '✅' if ok else '✗', '无 ✓' if not bad else '、'.join(bad), '无 ✓' if not ad else '有 ✗'))
        print('  开头:', t[:90].replace('\n', ' '))
        open(r'<项目目录>\Datasets\tmp\v2验收_%d字.md' % goal, 'w', encoding='utf-8').write(t)
    print('\n' + '=' * 64)
    print('总判定:', '✅ 长度可控训练生效' if all_ok else '❌ 未达标（详见各档）')


if __name__ == '__main__':
    main()
