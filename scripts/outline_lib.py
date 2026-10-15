# -*- coding: utf-8 -*-
"""大纲库解析库 —— 兼容卷内两种排版

背景：`04_剧情/` 下四卷的章级大纲排版不一致：
  第一卷  用管道表格      | 12 | 内容…… | 爽点…… |
  第二~四卷 用单元 + 条目   ### 【第X单元：…】（第 a - b 章）
                            - **第 12 章**：内容……
原 `outline_expand.py` 只认表格，导致二~四卷解析为 0 章、扩充器实际不可用。

本库统一两种格式，返回 {章号: {outline, payoff, unit}}，并提供跨卷的"后文走向"取用。
"""
import os, re

VAULT = r'<项目目录>\《自创作品》'
PLOT = os.path.join(VAULT, '04_剧情')

RE_UNIT = re.compile(r'^#{2,4}\s*(【?第[一二三四五六七八九十百\d]+单元[^】]*】?)')
RE_BULLET = re.compile(r'^[-*]\s*\*\*\s*第\s*(\d+)\s*章\s*\*\*\s*[:：]?\s*(.+)$')
RE_BULLET2 = re.compile(r'^[-*]\s*第\s*(\d+)\s*章\s*[:：]\s*(.+)$')
RE_RANGE = re.compile(r'(\d+)\s*章')
RE_HEAD = re.compile(r'^#\s+(第[一二三四五六七八九十]+卷[：:][^\n]*)')


def read(p):
    for enc in ('utf-8', 'gbk'):
        try:
            return open(p, encoding=enc).read()
        except Exception:
            continue
    return ''


def parse_volume(path):
    """返回 (卷标题, {章号: {outline,payoff,unit}}, 声明章数)"""
    txt = read(path)
    title, declared = os.path.basename(path)[:-3], None
    mh = RE_HEAD.search(txt)
    if mh:
        title = mh.group(1).strip()
    md = re.search(r'细化章级大纲\s*[（(]\s*(\d+)\s*章', txt)
    if md:
        declared = int(md.group(1))
    elif RE_RANGE.search(title):
        declared = int(RE_RANGE.search(title).group(1))

    chapters, unit = {}, ''
    for line in txt.split('\n'):
        s = line.strip()
        if not s:
            continue
        mu = RE_UNIT.match(s)
        if mu:
            unit = mu.group(1).strip()
            continue
        mb = RE_BULLET.match(s) or RE_BULLET2.match(s)
        if mb:
            n = int(mb.group(1))
            body = mb.group(2).strip()
            if len(body) > 8:
                chapters[n] = {'outline': body, 'payoff': '', 'unit': unit}
            continue
        if s.startswith('|'):
            cells = [c.strip() for c in s.strip('|').split('|')]
            if len(cells) >= 2 and re.fullmatch(r'\d+', cells[0]) and len(cells[1]) > 10:
                chapters[int(cells[0])] = {'outline': cells[1],
                                           'payoff': cells[2] if len(cells) > 2 else '',
                                           'unit': unit}
    return title, chapters, declared


def load_all(vault=VAULT):
    """返回 [{volume, title, chapters, declared}, ...]，按卷序 一二三四。"""
    plot = os.path.join(vault, '04_剧情')
    if not os.path.isdir(plot):
        return []
    order = ['一', '二', '三', '四', '五', '六']
    vols = []
    for fn in sorted(os.listdir(plot)):
        if not (fn.endswith('.md') and fn.startswith('第') and '卷' in fn):
            continue
        title, ch, declared = parse_volume(os.path.join(plot, fn))
        key = 99
        for i, c in enumerate(order):
            if fn.startswith('第' + c + '卷'):
                key = i
                break
        vols.append({'volume': fn[:-3], 'title': title, 'chapters': ch,
                     'declared': declared, 'order': key})
    vols.sort(key=lambda v: v['order'])
    return vols


def next_chapters(vols, vi, n, k=3):
    """跨卷取后文：本卷后续章，用尽则接下一卷开头。"""
    out = []
    for j in range(n + 1, n + 1 + k):
        if j in vols[vi]['chapters']:
            out.append((j, vols[vi]['chapters'][j]['outline']))
    if len(out) < k and vi + 1 < len(vols):
        nx = vols[vi + 1]['chapters']
        for j in sorted(nx)[:k - len(out)]:
            out.append((f'下一卷{j}', nx[j]['outline']))
    return out


if __name__ == '__main__':
    vs = load_all()
    print(f'共 {len(vs)} 卷')
    for v in vs:
        ch = v['chapters']
        rng = f'{min(ch)}~{max(ch)}' if ch else '无'
        print(f"  {v['volume']}: 解析 {len(ch)} 章（{rng}）  声明 {v['declared']}")
    # 抽样
    for v in vs:
        if v['chapters']:
            k = min(v['chapters'])
            print(f"\n[{v['volume']}] 第{k}章：{v['chapters'][k]['outline'][:70]}")
            break
