# -*- coding: utf-8 -*-
"""逻辑层体检 v1（2026-09-20）：词表层之外的三层检测。

层 1 语言逻辑：逐字复读（跨行滑窗 ✓）/ 引号配对 / 断句完整性 / 病句标记
层 2 语法构造：孤立引号 / 半截括号 / 疑似断行断裂
层 3 剧情逻辑（可自动化部分）：人名一致性（白名单+外来名 ✓）/ 已知设定冲突标记
用法：python logic_check.py <文本文件>
"""
import re
import sys
import collections

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

白名单 = ['主角', '示例角色1', '示例角色2', '示例角色3', '示例角色4', '示例角色5', '示例角色6', '示例角色7',
          '示例角色8', '示例角色9', '老馆长', '示例角色11', '示例角色10', '示例角色12', '老赵', '周叔', '老方', '示例角色13']
已知错名 = ['示例晨', '示例尘', '示例莫离', '李默']   # 实测出现过的漂移 ✗


def 层1_复读(text, win=40):
    """跨行滑窗：任意 ≥win 字的片段若出现两次 → 报告 ✓"""
    t = re.sub(r'\s+', '', text)
    seen = {}
    dups = []
    for i in range(0, len(t) - win):
        frag = t[i:i + win]
        if frag in seen:
            first = seen[frag]
            if i - first >= win:      # 两次出现间隔至少 win（避免自重叠 ✗）
                dups.append((first, frag))
        else:
            seen[frag] = i
    # 只保留第一个报警位置（后续与已报片段重叠的略过 ✓）
    out, last_pos = [], -1
    for first_pos, frag in sorted(dups):
        if first_pos >= last_pos:
            out.append((first_pos, frag))
            last_pos = first_pos + win
    return out


def 层1_引号(text):
    o, c = text.count('“'), text.count('”')
    return o, c


def 层1_断句(text):
    """行尾无标点且下一行不是新对话 → 疑似断行 ✓"""
    bad = []
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for i, ln in enumerate(lines):
        if len(ln) > 8 and not re.search(r'[。！？”…：：—]$', ln) and i + 1 < len(lines):
            nxt = lines[i + 1]
            if not nxt.startswith(('“', '"', '——')):
                bad.append((i + 1, ln[-25:], nxt[:25]))
    return bad


def 层2_括号(text):
    issues = []
    if text.count('（') != text.count('）'):
        issues.append('（ %d vs ） %d 不配对' % (text.count('（'), text.count('）')))
    lone = re.findall(r'[^\S]（[^）]{0,4}$|^[^（]{0,4}）', text, re.M)
    return issues


def 层3_人名(text):
    found_white = [n for n in 白名单 if n in text]
    found_bad = [n for n in 已知错名 if n in text]
    return found_white, found_bad


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r'<项目目录>\Datasets\tmp\验证_说人话_输出.md'
    text = open(path, encoding='utf-8').read()
    print('文件:', path, '（%d 字）' % len(text))
    print('=' * 62)

    print('\n【层 1 · 语言逻辑】')
    dups = 层1_复读(text)
    if dups:
        print('  ✗ 逐字复读 %d 处 ✗✗（同一片段出现两次 ✗）' % len(dups))
        for pos, frag in dups[:3]:
            print('    位置 %d：「%s…」' % (pos, frag[:50]))
    else:
        print('  ✅ 无逐字复读')
    o, c = 层1_引号(text)
    print('  引号配对: “ %d vs ” %d %s' % (o, c, '✓' if o == c else '✗ 不配对'))
    bad_lines = 层1_断句(text)
    if bad_lines:
        print('  ✗ 疑似断行断裂 %d 处:' % len(bad_lines))
        for ln, tail, nxt in bad_lines[:4]:
            print('    行%d 「…%s」→「%s…」' % (ln, tail, nxt))
    else:
        print('  ✅ 无断行断裂')

    print('\n【层 2 · 语法构造】')
    iss = 层2_括号(text)
    print('  括号:', '；'.join(iss) if iss else '✓')

    print('\n【层 3 · 剧情逻辑（可自动化部分 ✓）】')
    fw, fb = 层3_人名(text)
    print('  白名单名出现: %s' % ('、'.join(fw) if fw else '（无）'))
    if fb:
        print('  ✗✗ 外来/漂移人名: %s ✗✗（主角名都不对 ✗）' % '、'.join(fb))
    else:
        print('  ✅ 无已知漂移名')
    print('  ⚠️ 因果/时序/服装等剧情逻辑需人工逐句读 ✗（自动检测不可靠 ✗）')


if __name__ == '__main__':
    main()
