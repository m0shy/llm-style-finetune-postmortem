# -*- coding: utf-8 -*-
"""对比实验：原始大纲 vs 结构化大纲（结构化由我亲自撰写 ✓ 含动机/冲突/因果链 ✓）"""
import json
import re
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, r'<项目目录>\Datasets\scripts')
from length_control import INSTR, NAMES

API = 'http://127.0.0.1:8001/v1/chat/completions'

原始大纲 = ('主角给三妹买生日蛋糕，路过便利店目击红裙女人碎成光粒。'
           '他本能去抓落空，周围人毫无反应。他查监控、问路人确认是否幻觉。'
           '回到家发现小卖部变成面馆，老板坚称十年没换过招牌。')

结构化 = """【幕 1 · 生日蛋糕与裂痕】场景：下午，小卖部门口。人物：主角（动机：给三妹买蛋糕，心态放松）。
冲突：红裙女人在眼前碎成光粒，他抓了个空，周围人毫无反应。
因果：抓空加上无人反应，让他怀疑自己的眼睛，但性格使然他不声张，先暗自求证。
收尾钩：调出监控——录像里根本没有那个女人，他自己对着空气站了十分钟。
【幕 2 · 招牌的秘密】场景：傍晚，家楼下街道。人物：主角（动机：找到女人存在过的证据）。
冲突：常去的小卖部变成面馆，老板咬死十年没换过招牌，邻居也这么说。
因果：老板的话和记忆对不上，记忆与现实的裂缝第一次被证实。
细节：面馆招牌的样式、油锅味、老板在围裙上擦手——这些细节要自己长出来。
收尾钩：他翻出手机里小时候的旧照片，照片里这个位置，就是那家小卖部。
【幕 3 · 祝寿宴上的确认】场景：夜里，小爹酒楼包厢。人物：主角（表面贺寿，心里翻江倒海）、小爹示例角色6（不知情）。
冲突：小爹敬酒时随口一句"这片街十年前就规划过了"。
因果：这句话补上最后一块拼图——规划时间和面馆出现的时间吻合，不是幻觉，不是记错，是世界被人改过。
收尾钩：他握杯的手停住，抬头看了小爹一眼，什么都没说——他决定先藏着。"""

设定 = '【本作设定速查】主角主角，20 岁大二；三妹示例角色2 17（今天过生日）；父母失踪八年，由小爹示例角色6抚养。'
约束 = '【人物硬约束】除专名块名字外不得出现任何其他人名（店员/经理等一律无名化）；主角永远叫主角。'


def call(大纲文本, 目标字数, temp=0.8):
    instr = INSTR + '\n\n' + 设定 + '\n' + 约束
    instr += ('\n\n【本次要求】把上面的大纲扩写成一段连贯正文。'
              f'**目标长度约 {目标字数} 字**。写到自然段落结束即可。')
    inp = NAMES + '\n\n==== 本次要写 ====\n' + 大纲文本 + '\n'
    body = {'model': '自创作品', 'messages': [{'role': 'user', 'content': instr + '\n\n' + inp}],
            'max_tokens': int(目标字数 / 1.6 * 1.15), 'temperature': temp, 'top_p': 0.9,
            'repeat_penalty': 1.15}
    req = urllib.request.Request(API, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read().decode('utf-8'))
    return d['choices'][0]['message']['content']


def main():
    print('>>> A. 原始大纲（%d 字）→ 目标 800' % len(原始大纲))
    A = call(原始大纲, 800)
    print('    生成 %d 字' % len(A))
    open(r'<项目目录>\Datasets\tmp\对比_A_原始大纲.md', 'w', encoding='utf-8').write(A)

    print('>>> B. 结构化大纲（%d 字）→ 3 幕 × 目标 270' % len(结构化))
    幕文本s = re.split(r'(?=【幕 \d)', 结构化.strip())
    幕文本s = [x.strip() for x in 幕文本s if x.strip()]
    B_parts = []
    for i, 幕 in enumerate(幕文本s, 1):
        t = call(幕, 270)
        B_parts.append(t)
        print('    幕 %d: %d 字' % (i, len(t)))
    B = '\n\n'.join(B_parts)
    open(r'<项目目录>\Datasets\tmp\对比_B_结构化大纲.md', 'w', encoding='utf-8').write(B)
    print('    B 合计 %d 字' % len(B))
    print('✓ 两份输出已存 ✓（接下来由我逐句亲读 ✓）')


if __name__ == '__main__':
    main()
