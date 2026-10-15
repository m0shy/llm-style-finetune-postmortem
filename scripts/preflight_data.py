# -*- coding: utf-8 -*-
"""训练前数据预检（纯 CPU，不需要 GPU）

为什么必须做：
  1. 上一次训练就是栽在数据层（metadata 字段类型冲突，Arrow 直接抛错），白等一场。
  2. cutoff_len 是硬截断，超出部分的**标签会被丢掉**。多要点样本输出中位 1697 字，
     必须确认它们不会被截掉尾巴，否则"写全要点"这个训练目标本身就废了。

做法：用基座模型自带的 tokenizer + Qwen 对话模板，把每条样本拼成真正的训练输入，
      统计 token 数，并与 cutoff_len 比对。

用法：python scripts/preflight_data.py --data <jsonl> --cutoff 2048
"""
import json, os, sys, argparse, statistics, collections

try:
    sys_stdout_needed = True
except Exception:
    pass
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = r'<项目目录>\Models\models\Qwen--Qwen2.5-7B-Instruct'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=r'<项目目录>\LLaMA-Factory\data\dataset_multi_v8base.jsonl')
    ap.add_argument('--cutoff', type=int, default=2048)
    ap.add_argument('--sample', type=int, default=400)
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.data, encoding='utf-8') if l.strip()]
    print(f'样本总数 {len(rows)}')

    # ---- 1. 结构检查 ----
    bad = []
    for i, r in enumerate(rows):
        for k in ('instruction', 'input', 'output'):
            if not isinstance(r.get(k), str):
                bad.append((i, k, type(r.get(k)).__name__))
        if not r.get('instruction', '').strip():
            bad.append((i, 'instruction', 'empty'))
        if not r.get('output', '').strip():
            bad.append((i, 'output', 'empty'))
    print(f'[结构] 字段类型/空值问题：{len(bad)} 处', bad[:5])

    # ---- 2. metadata 类型一致性（上次训练的崩因）----
    keys = collections.defaultdict(set)
    for r in rows:
        for k, v in (r.get('metadata') or {}).items():
            keys[k].add(type(v).__name__)
    mixed = {k: v for k, v in keys.items() if len(v) > 1}
    print(f'[metadata] 字段：{sorted(keys)}')
    print(f'[metadata] 类型不一致的字段：{mixed if mixed else "无"}')


    # ---- 4. 越界检查（硬性拦截）：训练集不得含用户自己的世界观 ----
    # 用户 2026-09-12 明确指示：
    #   「我的大纲中的所有数据都不允许作为训练素材，因为它们都是不合格的，
    #     目前只有那五本网文是合格的，我的大纲只能作为一个检测的样本」
    # 所以这里**必须是硬失败**（exit 2），不能只是打印警告 —— 越界一次就等于整轮白训。
    #
    # 注意：特征词只收**用户世界独有的专名**，不要收「权柄/指南针/怀表/希冀」这类
    # 通用词 —— 它们既是用户的卡名，也大量出现在源书里，收进来全是误报
    # （实测误报过 8 个词，逐个查上下文才排清）。
    USER_ONLY = [
        '主角', '示例角色1', '示例角色2', '示例角色7', '示例角色6', '示例角色4', '示例角色5',
        '示例角色14', '示例角色12', '示例角色8', '示例角色10', '示例角色15',
        '示例设定A', '示例设定B', '示例设定C', '示例设定D', '示例设定E', '示例设定F', '示例设定T',
        '示例设定G', '示例设定H', '示例设定I', '示例设定J', '示例设定L',
        '示例设定K', '示例设定M', '示例设定N', '示例设定O', '示例设定P',
    ]
    leak = {}
    for w in USER_ONLY:
        n = sum(1 for r in rows
                if w in r.get('input', '') or w in r.get('output', '')
                or w in r.get('instruction', ''))
        if n:
            leak[w] = n
    if leak:
        print(f'[越界] *** 训练集里出现用户世界观专名，违反用户明确指示，构建中止：{leak}')
        sys.exit(2)
    print('[越界] 训练集不含用户世界观内容 ✓（用户指示：只有那五本网文可作为训练素材）')

    # ---- 3. 模板 tokenize，量真实长度 ----
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(BASE, trust_remote_code=True)
    print(f'[tokenizer] 已加载 {getattr(tok, "name_or_path", "?")}')

    stats = collections.defaultdict(list)
    over = collections.defaultdict(int)
    worst = []
    for r in rows:
        t = r.get('metadata', {}).get('task', '?')
        user = r['instruction'] + ('\n' + r['input'] if r['input'] else '')
        prompt = tok.apply_chat_template([{"role": "user", "content": user}],
                                         tokenize=False, add_generation_prompt=True)
        n_p = len(tok(prompt)['input_ids'])
        n_o = len(tok(r['output'])['input_ids']) + 1
        total = n_p + n_o
        stats[t].append((n_p, n_o, total))
        if total > a.cutoff:
            over[t] += 1
        worst.append((total, t, r.get('metadata', {}).get('loc', '')))

    print(f'\ncutoff_len = {a.cutoff}')
    print(f'{"任务":<12}{"条数":>6}{"prompt中位":>10}{"输出中位":>10}{"合计中位":>10}{"合计最大":>10}{"超限条数":>10}')
    for t, v in sorted(stats.items()):
        ps = sorted(x[0] for x in v)
        os_ = sorted(x[1] for x in v)
        ts = sorted(x[2] for x in v)
        print(f'{t:<12}{len(v):>6}{ps[len(ps)//2]:>10}{os_[len(os_)//2]:>10}'
              f'{ts[len(ts)//2]:>10}{ts[-1]:>10}{over.get(t,0):>10}')

    tot_over = sum(over.values())
    print(f'\n超出 cutoff 会被截断的样本：{tot_over} / {len(rows)} ({tot_over/len(rows)*100:.1f}%)')
    worst.sort(reverse=True)
    print('最长的 5 条：', worst[:5])


if __name__ == '__main__':
    main()
