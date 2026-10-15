# -*- coding: utf-8 -*-
"""A/B 对照生成测试：基座 vs 微调后，同 prompt 同种子

为什么要"同 prompt 同种子"：
  文风对比最容易犯的错是"换了种子/换了 prompt 就下结论"——
  生成本身方差很大，不控变量的话两次输出差异里有多少是模型变了、多少是随机性，分不清。

用法：
    python ab_generate.py --models base,outputs/cpt_v2/checkpoint-275 --out ab_result.md
    python ab_generate.py --models base,outputs/cpt_v1/checkpoint-150,outputs/cpt_v2/checkpoint-275

输出：每个 prompt 下、每个模型的一段正文 + 自动指标，落成 markdown 便于逐行读。
"""
import os, sys, json, time, argparse

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_MODEL = r'<项目目录>\Models\models\Qwen--Qwen2.5-7B-Instruct'

PROMPTS = [
    ('都市日常·面馆', '他推门进来，面馆里只有三张桌子。老板娘正在擦最后一张，抬头看了他一眼，手上的布没停。'),
    ('对话·两个人拌嘴', '"你要是早说一句，我就不用跑这一趟。"她把包往桌上一放，"现在倒好，全怪我。"'),
    ('紧张·追上来', '脚步声从楼道那头传过来，不快，但一步比一步近。他数着步子，手已经按在门把上。'),
]

SYS = '你是一个中文网络小说写手。接着下面这段文字往下写一段正文，三百字左右。'


def load(model_spec):
    """model_spec: 'base' 或适配器目录路径"""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    bnb = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type='nf4',
        bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=False)  # 2026-09-16：double_quant 会触发 CUDA 越界
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, quantization_config=bnb, device_map='auto', trust_remote_code=True)
    if model_spec != 'base':
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, model_spec)
    model.eval()
    return tok, model


def gen(tok, model, prompt):
    import torch
    msgs = [{'role': 'system', 'content': SYS}, {'role': 'user', 'content': prompt}]
    text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(text, return_tensors='pt').to(model.device)
    with torch.no_grad():
        out = model.generate(
            **ids, max_new_tokens=420, do_sample=True,
            temperature=0.65, top_p=0.9, top_k=40, repetition_penalty=1.1,
            no_repeat_ngram_size=4,
            pad_token_id=tok.pad_token_id or tok.eos_token_id,
            stop_strings=['\nuser', '\nassistant', '<|im_end|>'], tokenizer=tok)
    return tok.decode(out[0][ids['input_ids'].shape[1]:], skip_special_tokens=True).strip()


def metrics(text):
    sys.path.insert(0, r'<项目目录>\Datasets\scripts')
    try:
        from ai_tells import metrics as am, TELL_WORDS
        m = am(text)
        tell = sum(text.count(w) for w in TELL_WORDS) / max(len(text), 1) * 1000
        import re
        sents = [s for s in re.split(r'[。！？…]+', text) if s.strip()]
        avg = sum(len(s) for s in sents) / max(len(sents), 1)
        return {'指纹词/千字': round(tell, 2), '段方差': round(m['段落长度方差'], 0),
                '句数': len(sents), '平均句长': round(avg, 1), '字数': len(text)}
    except Exception as e:
        return {'错误': str(e)[:60]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', required=True, help='逗号分隔，base 或适配器路径')
    ap.add_argument('--out', default=r'<项目目录>\Datasets\tmp\ab_result.md')
    a = ap.parse_args()
    specs = [s.strip() for s in a.models.split(',') if s.strip()]

    import torch
    torch.manual_seed(20260916)   # 固定种子：让对比可控

    lines = ['# A/B 对照生成测试', f'种子 20260916 | temperature 0.65 | top_p 0.9 | 每段 420 token', '']
    results = []
    for spec in specs:
        label = '基座' if spec == 'base' else os.path.basename(spec.rstrip('\\/'))
        print(f'--- 加载 {label} ---', flush=True)
        t0 = time.time()
        try:
            tok, model = load(spec)
        except Exception as e:
            lines.append(f'## {label}\n加载失败：{e}\n')
            continue
        print(f'    加载耗时 {time.time()-t0:.0f}s', flush=True)
        lines.append(f'## {label}')
        lines.append('')
        for pname, prompt in PROMPTS:
            torch.manual_seed(20260916)          # 每个 prompt 前重置，保证各模型同起点
            print(f'    生成 {pname} ...', flush=True)
            try:
                txt = gen(tok, model, prompt)
            except Exception as e:
                txt = f'（生成失败：{e}）'
            m = metrics(txt)
            lines.append(f'### {pname}')
            lines.append(f'**指标** {json.dumps(m, ensure_ascii=False)}')
            lines.append('')
            lines.append(f'> 上文：{prompt}')
            lines.append('')
            lines.append(txt)
            lines.append('')
            results.append((label, pname, m))
        del model
        import gc; gc.collect()
        try:
            import torch as _t; _t.cuda.empty_cache()
        except Exception:
            pass

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, 'w', encoding='utf-8').write('\n'.join(lines))
    print(f'\n结果已写入：{a.out}')


if __name__ == '__main__':
    main()
