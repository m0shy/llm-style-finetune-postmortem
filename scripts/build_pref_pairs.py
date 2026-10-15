# -*- coding: utf-8 -*-
"""构建偏好对 —— 给 DPO / SimPO 用（学"用法与判断"）

为什么需要（2026-09-15 查证）：
  SFT 学"应该输出什么"（模仿单一答案）；**偏好优化学"A 比 B 好在哪"** —— 学的是相对好坏。
  而"AI 使用逻辑"恰恰是相对判断（同一位置，这样写比那样写好），
  所以**只有偏好优化能直接教"哪种更好"**。指令只能约束"用多少"，SFT 只能模仿"长什么样"。

设计（关键：正例用**真人原文**，不用我的指标打分）
  prompt    = 同一份章级大纲（与 SFT 样本同源 → 保证不分布漂移）
  chosen    = **卖报写的真实正文**（就是那条 SFT 样本的 output）
  rejected  = **模型自己针对同一 prompt 的产出**

  ⚠️ 为什么不用"我的指标打分"当正例选择依据：那会**奖励欺骗**（Goodhart）——
     模型学会刷分而不是写好。用真人原文当正例，信号来自真人的笔，无法被刷。

⚠️ 五条风险的对策（查证所得）
  1. 奖励欺骗 → 正例一律用真人原文（本脚本已保证）
  2. 长度偏置 → 组装时打印 chosen/rejected 的长度分布，长度差过大的对丢掉
  3. 退化    → 训练侧 β 调高、只跑 1 epoch
  4. 分布漂移 → prompt 与真实用法同源（用 SFT 样本的 prompt）
  5. 成对胜率 → 训完必须量（见 eval_all 之外的单测）

用法：
  # ① 先跑生成（要占 GPU）——把模型对每条 prompt 的产出存下来
  python scripts/build_pref_pairs.py --adapter <SFT后适配器> --limit 800 --generate

  # ② 再组装（纯 CPU）
  python scripts/build_pref_pairs.py --assemble
"""
import os, sys, json, random, argparse

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

LF = r'<项目目录>\LLaMA-Factory'
SFT_DATA = os.path.join(LF, 'data', 'dataset_multi_v20.jsonl')
GEN_OUT = os.path.join(r'<项目目录>\Datasets', 'tmp', 'pref_generated.jsonl')
PAIR_OUT = os.path.join(r'<项目目录>\Datasets', 'data_dual', 'dataset_pref_pairs.jsonl')
LEN_RATIO_MAX = 3.0      # chosen/rejected 长度比超过这个就丢掉（防长度偏置）


def rows():
    return [json.loads(l) for l in open(SFT_DATA, encoding='utf-8') if l.strip()]


def do_generate(a):
    """用模型对每条 prompt 生成一个 rejected 版本。"""
    from probe_one import load_model, run
    rs = rows()
    # 优先用"大纲式"样本（prompt 形态最接近真实用法：给大纲写正文）
    ol = [r for r in rs if r.get('metadata', {}).get('task') in ('outline', 'multibeat')]
    random.Random(7).shuffle(ol)
    ol = ol[:a.limit]
    print(f'待生成 {len(ol)} 条（从大纲式/多要点样本里取）')

    model, tok = load_model(a.adapter)
    with open(GEN_OUT, 'w', encoding='utf-8') as f:
        for i, r in enumerate(ol, 1):
            prompt = (r['instruction'] or '') + '\n\n' + (r['input'] or '')
            out = run(model, tok, prompt, a.max_new)
            f.write(json.dumps({'prompt': prompt, 'chosen': r['output'],
                                'rejected': out}, ensure_ascii=False) + '\n')
            if i % 20 == 0:
                print(f'  {i}/{len(ol)}')
    print(f'生成完毕 -> {GEN_OUT}')


def do_assemble(a):
    if not os.path.isfile(GEN_OUT):
        print(f'找不到 {GEN_OUT}，先跑 --generate')
        return
    pairs, dropped_len, dropped_same = [], 0, 0
    for l in open(GEN_OUT, encoding='utf-8'):
        if not l.strip():
            continue
        d = json.loads(l)
        c, rj = d['chosen'].strip(), d['rejected'].strip()
        if not c or not rj:
            continue
        # 长度偏置控制：两边长度差太多就丢（否则模型学会"越长越好"）
        ratio = max(len(c), len(rj)) / max(min(len(c), len(rj)), 1)
        if ratio > LEN_RATIO_MAX:
            dropped_len += 1
            continue
        # 两边太像（模型已复述原文）→ 无偏好信号，丢掉
        if c[:60] == rj[:60]:
            dropped_same += 1
            continue
        pairs.append({'instruction': d['prompt'][:4000], 'input': '',
                      'chosen': c, 'rejected': rj,
                      'metadata': {'task': 'pref'}})
    random.Random(7).shuffle(pairs)
    os.makedirs(os.path.dirname(PAIR_OUT), exist_ok=True)
    with open(PAIR_OUT, 'w', encoding='utf-8') as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + '\n')
    L = [len(p['chosen']) for p in pairs]
    R = [len(p['rejected']) for p in pairs]
    print(f'偏好对 -> {PAIR_OUT}')
    print(f'  共 {len(pairs)} 对（丢长度偏置 {dropped_len}、丢太像 {dropped_same}）')
    print(f'  chosen 长度  中位 {sorted(L)[len(L)//2]} 字')
    print(f'  rejected 长度 中位 {sorted(R)[len(R)//2]} 字')
    print(f'  → 中位长度比 {sorted(R)[len(R)//2]/max(sorted(L)[len(L)//2],1):.2f}')
    print('\n注册（dataset_info.json）：')
    print('  "pref_pairs": {"file_name": "dataset_pref_pairs.jsonl", "ranking": true,')
    print('                 "columns": {"prompt": "instruction", "chosen": "chosen", "rejected": "rejected"}}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--adapter')
    ap.add_argument('--limit', type=int, default=800)
    ap.add_argument('--max-new', type=int, default=1400)
    ap.add_argument('--generate', action='store_true')
    ap.add_argument('--assemble', action='store_true')
    a = ap.parse_args()
    if a.generate:
        if not a.adapter:
            print('--generate 需要 --adapter')
            return
        do_generate(a)
    if a.assemble or not a.generate:
        do_assemble(a)


if __name__ == '__main__':
    main()
