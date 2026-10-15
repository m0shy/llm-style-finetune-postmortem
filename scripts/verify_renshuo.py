# -*- coding: utf-8 -*-
"""「说人话」验证：完整指令 + 完整输出 + 逐项体检（2026-09-20）。

用户标准（创作铁律 #6 ✓）：
  禁破折号 / 禁链式排比 / 禁"不是A而是B" / 禁总结癖意义宣告
  情绪外化 ✗ 直陈 / 禁 AI 高频词 / 禁副词堆叠 / 禁比喻滥用 / 禁半角标点
"""
import json
import re
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, r'<项目目录>\Datasets\scripts')
from length_control import 生成控长, INSTR, NAMES

大纲 = ('主角给三妹买生日蛋糕，路过便利店目击红裙女人碎成光粒。'
       '他本能去抓落空，周围人毫无反应。他查监控、问路人确认是否幻觉。'
       '回到家发现小卖部变成面馆，老板坚称十年没换过招牌。')

目标 = 800
正文, ntok = 生成控长(大纲, 目标, 温度=0.8)

# ============ 完整指令还原（给用户看 ✓）============
完整指令 = INSTR + ('\n\n【本次要求】把上面的大纲扩写成一段连贯正文。'
                   f'**目标长度约 {目标} 字**。写到自然段落结束即可。')
完整输入 = NAMES + '\n\n==== 本次要写 ====\n章级大纲：' + 大纲 + '\n'

print('#' * 66)
print('# 一、完整指令（模型实际收到的一切 ✓）')
print('#' * 66)
print()
print('---- [system 语义 · INSTRUCTION] ----')
print(完整指令)
print()
print('---- [user 语义 · 输入块] ----')
print(完整输入)
print()

print('#' * 66)
print('# 二、模型输出（全文 ✓ 共 %d 字 / %d token）' % (len(正文), ntok))
print('#' * 66)
print()
print(正文)
print()

print('#' * 66)
print('# 三、「说人话」体检（逐项 ✓）')
print('#' * 66)
print()

检查 = [
    ('破折号（你禁 ✓）', '——|──|—'),
    ('AI 高频词', '嘴角勾起|嘴角上扬|眼神深邃|眼中闪过一丝|微微挑眉|沉吟片刻|心中一凛|心中一沉|心中一动|心下了然|顿时|瞬间|愈发|略微|一时之间'),
    ('情绪直陈 ✗', '心里一酸|心中一暖|松了一口气|感到一阵|意识到|明白了'),
    ('副词堆叠', '小心翼翼地|淡淡地|深深地|缓缓地|轻轻地'),
    ('比喻滥用（仿佛/宛如/犹如）', '仿佛|宛如|犹如|恍若'),
    ('"不是A而是B"句式', '不是[^。，]{1,12}而是'),
    ('链式排比（三个"的"连缀≥3组）', '[^。，]{8,}的[^。，]{2,8}的[^。，]{2,8}的[^。，]{2,8}的'),
    ('半角标点', '[,;](?![0-9])'),
    ('网络语/英文', 'OMG|绝绝子|yyds|CPU|KPI|OK'),
    ('指纹词（大模型味 ✓）', '血色|猩红|空气仿佛凝固|时间仿佛静止'),
]
bad_total = 0
for name, pat in 检查:
    hits = re.findall(pat, 正文)
    mark = '✅ 无' if not hits else '✗ %d 处: %s' % (len(hits), '、'.join(dict.fromkeys(hits))[:80])
    if hits:
        bad_total += len(hits)
    print('  %-22s %s' % (name, mark))

print()
# 句长
sents = [s.strip() for s in re.split(r'(?<=[。！？”])', 正文) if s.strip()]
ls = sorted(len(s) for s in sents)
print('  句子统计: %d 句 | 平均 %.1f 字 | 中位 %d | 最短 %d | 最长 %d' % (
    len(sents), sum(ls)/len(ls), ls[len(ls)//2], ls[0], ls[-1]))
short = sum(1 for x in ls if x <= 12)
print('  短句（≤12 字）占比: %.0f%%（卖报特征 ✓ 高一些好 ✓）' % (100*short/len(sents)))
print()
print('  总扣分项: %d 处 %s' % (bad_total, '✅ 达标' if bad_total == 0 else '⚠️ 见上表'))
