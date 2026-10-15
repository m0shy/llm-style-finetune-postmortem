# -*- coding: utf-8 -*-
"""章节生成器（本地直连，不需要起 API 服务）

与 `outline_expand.py` 的区别：
  outline_expand.py 走 OpenAI 兼容接口（要另起 vLLM / llama.cpp 服务）；
  本脚本直接在本机 GPU 上加载「基座 + LoRA 适配器」推理，一步到位。

要点：
  - 三段式 prompt：本次要写 / 后文走向（供对齐，严禁提前写出）/ 硬约束（人物卡+设定卡+伏笔台账）
  - 按 beat 分段生成，每段单独喂硬约束，降低长程跑偏
  - 带 stop_strings，避免模型把 `user` 角色标记当正文吐出来（v3 评测踩过这个坑）
  - 生成完顺手跑一遍 chapter_qa 质检

用法：
  python gen_chapter.py --volume "第二卷" --chapter 3 --adapter outputs/v5_multi --out ch02-03.md
  python gen_chapter.py --volume "第二卷" --chapter 3 --dry-run     # 只打印 prompt
"""
import os, re, sys, io, time, argparse

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from outline_expand import (SYS_RULES, parse_chapters, collect_constraints,
                            split_beats, build_prompt)     # noqa: E402
from outline_lib import next_chapters                        # noqa: E402
from chapter_qa import strip_dash                            # noqa: E402

BASE = r'<项目目录>\Models\models\Qwen--Qwen2.5-7B-Instruct'
STOPS = ["<|im_end|>", "<|im_start|>", "\nuser", "\nassistant", "\n<|"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--volume', required=True)
    ap.add_argument('--chapter', type=int, required=True)
    ap.add_argument('--adapter', default=r'<项目目录>\LLaMA-Factory\outputs\v5_multi')
    ap.add_argument('--beats', type=int, default=3)
    ap.add_argument('--out', default=None)
    ap.add_argument('--max-new', type=int, default=900)
    ap.add_argument('--temperature', type=float, default=0.65)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    hit, vols = parse_chapters(a.volume)
    chapters, volume, vi = hit['chapters'], hit['volume'], vols.index(hit)
    if a.chapter not in chapters:
        raise SystemExit(f'《{volume}》没有第 {a.chapter} 章（范围 {min(chapters)}~{max(chapters)}）')
    nxt = next_chapters(vols, vi, a.chapter, 3)
    cons = collect_constraints(volume, chapters[a.chapter]['outline'])
    beats = split_beats(chapters[a.chapter]['outline'], a.beats)
    print(f'《{volume}》第{a.chapter}章 → {len(beats)} 段；注入约束 {len(cons)} 份；后文 {len(nxt)} 章')

    if a.dry_run:
        print('=' * 88)
        print(build_prompt(volume, a.chapter, chapters, cons, 1, len(beats), nxt))
        return

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel

    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16,
                             bnb_4bit_use_double_quant=False)   # 2026-09-16 修缮：True 会触发 CUDA 越界
    tok = AutoTokenizer.from_pretrained(BASE, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(BASE, quantization_config=bnb,
                                                 device_map="auto", trust_remote_code=True)
    if os.path.isfile(os.path.join(a.adapter, 'adapter_model.safetensors')):
        model = PeftModel.from_pretrained(model, a.adapter)
    else:
        print(f'[WARN] 未找到适配器，使用基座：{a.adapter}')
    model.eval()

    def gen(prompt):
        txt = tok.apply_chat_template([{"role": "user", "content": prompt}],
                                      tokenize=False, add_generation_prompt=True)
        ids = tok(txt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=a.max_new, do_sample=True,
                                 temperature=a.temperature, top_p=0.9, top_k=40,
                                 repetition_penalty=1.05, no_repeat_ngram_size=8,
                                 pad_token_id=tok.eos_token_id, tokenizer=tok,
                                 stop_strings=STOPS)
        s = tok.decode(out[0][ids['input_ids'].shape[1]:], skip_special_tokens=True)
        for m in STOPS:
            if m in s:
                s = s.split(m)[0]
        return strip_dash(s.strip())      # 作者禁用破折号，源书里却大量使用，必须后处理

    parts = []
    prev_tail = ''
    for i in range(len(beats)):
        p = build_prompt(volume, a.chapter, chapters, cons, i + 1, len(beats), nxt)
        # 关键：第 2 段起必须把前面已生成的正文带进 prompt。
        # 否则各段各写各的，接不上：第 2 段不知道第 1 段写了什么，
        # 会重复开场、场景状态断裂。带上前文末尾后，后续段落实质上变成
        # 「前文 → 续写」任务——这正是续写样本训练过的形态，模型是会的。
        if prev_tail:
            p += ('\n\n==== 前文末尾（衔接用，接下去写，不要复述）====\n' + prev_tail)
        t0 = time.time()
        seg = gen(p)
        print(f'  第 {i+1}/{len(beats)} 段：{len(seg)} 字，用时 {time.time()-t0:.0f}s')
        parts.append(seg)
        prev_tail = ('\n'.join(parts))[-700:]      # 带最后 700 字，够衔接又不至于挤占预算

    text = f'# {volume} 第{a.chapter}章\n\n' + '\n\n'.join(x for x in parts if x)
    out_path = a.out or f'ch{a.chapter:02d}.md'
    open(out_path, 'w', encoding='utf-8').write(text)
    print(f'\n已写出 {out_path}（{len(text)} 字）')
    print('提示：分段生成的接缝需人工过一遍；接着跑 chapter_qa.py 做交付前质检。')


if __name__ == '__main__':
    main()
