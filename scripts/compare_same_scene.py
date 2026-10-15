# -*- coding: utf-8 -*-
"""同场景对比 —— 把「模型续写」和「作者本人续写」放在同一位置比

为什么需要：
  `style_gap.py` 是拿产出和**整本原著的平均**比。这有个混杂：我的探针全是高戏剧强度场景
  （掀桌/诀别/感情戏），而基准线是全书平均 —— 高戏剧场景天然比喻和情绪更多，
  比出来"AI 腔重"可能只是场景差异造成的假象。

  这个工具换成**同一场戏、同一位置**：
      作者写到这里之后是怎么写的  vs  模型写到这里之后是怎么写的
  两个文本上下文完全一致，唯一的差别就是"谁写的"。**这是最干净的对照。**

  实测价值（2026-09-13）：同一场戏，卖报本人「直陈情绪 0.0 / 比喻词 0.0 每千字」，
  模型「1.99 / 3.98」——把"AI 腔"从感觉变成了确凿的数字。

用法：
  python scripts/compare_same_scene.py --probe-output 模型产出.txt \
      --source "C:\\...\\大奉打更人(501-955章).txt" --anchor "宋卿作为如今司天监的扛把子"
"""
import os, sys, json, argparse

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style_gap import metrics   # noqa: E402


def read(p):
    for enc in ('utf-8', 'gbk'):
        try:
            return __import__('scan_noise').read_text(p)   # 2026-09-16 统一修缮：原 errors='ignore' 对 GBK 静默出错
        except Exception:
            continue
    return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe-output', required=True, help='模型产出（.txt/.md 或含 output 的 json）')
    ap.add_argument('--source', required=True, help='源书 txt')
    ap.add_argument('--anchor', required=True, help='探针输入里的一句特征话，用来在源书里定位')
    ap.add_argument('--len', type=int, default=560, help='截取长度，默认 560 字')
    a = ap.parse_args()

    src = read(a.source)
    i = src.find(a.anchor)
    if i < 0:
        print(f'在源书里找不到锚点「{a.anchor}」，换个更独特的句子。')
        return
    j = src.find('\n', src.find('。', i) + 1)
    real = src[j:j + a.len].strip()

    out = read(a.probe_output)
    if out.lstrip().startswith(('{', '[')):
        try:
            d = json.loads(out)
            out = d['output'] if isinstance(d, dict) else out
        except Exception:
            pass
    model = out[:a.len]

    keys = ['直陈情绪 每千字', '比喻词 每千字', '套话连接词 每千字', '升华句 每千字',
            '平均句长', '句长波动(标准差)', '平均段长', '段长波动(标准差)', '对白占比%']
    mr, mm = metrics(real), metrics(model)

    print(f'===== 同场景对比（锚点「{a.anchor[:16]}…」各取 {a.len} 字）=====\n')
    print(f'{"指标":<18}{"作者本人":>10}{"模型":>10}{"差":>10}')
    worse = []
    for k in keys:
        d = mm[k] - mr[k]
        flag = ''
        # 「多余」的判定：作者写得克制而模型写得多，才是真问题
        if k in ('直陈情绪 每千字', '比喻词 每千字', '套话连接词 每千字', '升华句 每千字'):
            if d > max(0.3, mr[k] * 0.5 + 0.3):
                flag = '  ← 模型多写了'
                worse.append(k)
        elif k in ('句长波动(标准差)', '段长波动(标准差)') and mr[k] > 0 and d < -mr[k] * 0.3:
            flag = '  ← 模型更平'
            worse.append(k)
        print(f'{k:<18}{mr[k]:>10}{mm[k]:>10}{d:>+10.2f}{flag}')

    print()
    if worse:
        print(f'模型相对作者多写/写平的地方：{len(worse)} 项 —— ' + '、'.join(worse))
        print('这几项就是下一轮要压的。')
    else:
        print('与作者本人的写法看不出实质差别。')

    print('\n----- 作者原文（前 300 字）-----')
    print(real[:300].replace('\n', ' '))
    print('\n----- 模型产出（前 300 字）-----')
    print(model[:300].replace('\n', ' '))


if __name__ == '__main__':
    main()
