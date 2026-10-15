# -*- coding: utf-8 -*-
"""大纲 → 章节 编排器（绕过 7B 不会写长篇的结构性短板）

思路: 不指望模型一次吐 4000 字整章（它做不到），而是
  ① 把章节大纲拆成 N 个"场景 beat"
  ② 每个 beat 单独调用微调模型（现有片段级能力正好适配）
  ③ 拼接 + 跨 beat 去重 + 一致性收尾

对接任意 OpenAI 兼容端点（vLLM / ollama / LM Studio / 中转 API）。

用法:
  # 1) 大纲写在文件里，每段一个 beat（空行/换行分隔）
  python scripts/outline_to_chapter.py --outline-file beat.txt --out out.md

  # 2) 直接传一段大纲，脚本按句号自动切成 4~6 个 beat
  python scripts/outline_to_chapter.py --outline "……" --beats 5 --out ch01.md

  # 3) 指定端点与采样参数
  python scripts/outline_to_chapter.py --outline-file beat.txt ^
      --api-base http://localhost:8000/v1 --model Qwen2.5-7B-Lingjing ^
      --temperature 0.8 --repetition-penalty 1.2 --no-repeat-ngram 4

依赖: pip install requests   （或把 _chat() 换成你的 SDK）
"""
import json, os, re, sys, io, random, argparse, time

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass

# 与训练集对齐的指令变体（v2 数据打散后的 10 种，随机取一种）
TPL = [
    "剧情：{outline}\n请据此写一段小说正文。画面感强、节奏张弛有度，长短句交错；注重感官描写；用动作和微表情展现心理，不要直接陈述情绪；禁用“首先/其次/总之”。",
    "请依据以下剧情扩写小说正文。画面感强、节奏张弛有度，长短句交错；注重感官描写；以动作和微表情写心理，不直陈情绪；禁用公文连接词。剧情：\n{outline}",
    "把下面这段剧情写成小说正文片段。要画面、要节奏，长短句混排；心理靠动作与微表情呈现；不要直说情绪。\n{outline}",
    "以下是剧情大纲，请撰写小说正文片段。感官细节充分，长短句交错，情绪外化，不出现公文连接词。\n{outline}",
]


def _chat(api_base, model, prompt, temperature, top_p, rep, ngram, max_new, timeout=120):
    """调用 OpenAI 兼容 /chat/completions。失败时抛出可读异常。"""
    import requests
    url = api_base.rstrip('/') + '/chat/completions'
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_new,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.2,
    }
    # vLLM 支持 extra：repetition_penalty / no_repeat_ngram_size；ollama/多数中转忽略
    if rep:
        body["repetition_penalty"] = rep
    if ngram:
        body["no_repeat_ngram_size"] = ngram
    r = requests.post(url, json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def split_beats(text, n=None):
    """把大纲切成 beat。优先按空行/换行；否则按句号切分后均匀分组。"""
    paras = [p.strip() for p in re.split(r'\n\s*\n|\n', text) if p.strip()]
    if len(paras) >= 2:
        return paras
    sents = [s.strip() for s in re.split(r'(?<=[。！？；])', text) if s.strip()]
    if not sents:
        return [text.strip()]
    k = n or min(6, max(3, len(sents) // 2))
    k = min(k, len(sents))
    size = (len(sents) + k - 1) // k
    return [''.join(sents[i:i + size]) for i in range(0, len(sents), size)]


def dedupe_sentences(text):
    """跨段落去重：同一句话（≥6 字）只保留首次出现，防复读。"""
    seen, out = set(), []
    for para in text.split('\n'):
        p = para.strip()
        if not p:
            out.append('')
            continue
        kept = []
        for s in re.split(r'(?<=[。！？…])', p):
            key = re.sub(r'[\s　“”"\'』]', '', s)
            if len(key) >= 6 and key in seen:
                continue
            if len(key) >= 6:
                seen.add(key)
            kept.append(s)
        out.append(''.join(kept))
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--outline-file')
    ap.add_argument('--outline')
    ap.add_argument('--beats', type=int, default=None, help='期望 beat 数（默认自动）')
    ap.add_argument('--api-base', default=os.environ.get('LLM_API_BASE', 'http://localhost:8000/v1'))
    ap.add_argument('--model', default=os.environ.get('LLM_MODEL', 'Qwen2.5-7B-Lingjing'))
    ap.add_argument('--temperature', type=float, default=0.8)
    ap.add_argument('--top-p', type=float, default=0.9)
    ap.add_argument('--repetition-penalty', type=float, default=1.2)
    ap.add_argument('--no-repeat-ngram', type=int, default=4)
    ap.add_argument('--max-new-tokens', type=int, default=900)
    ap.add_argument('--out', default='chapter.md')
    ap.add_argument('--seed', type=int, default=42)
    a = ap.parse_args()

    text = a.outline if a.outline else open(a.outline_file, encoding='utf-8').read()
    beats = split_beats(text, a.beats)
    random.seed(a.seed)
    print(f'共 {len(beats)} 个 beat，端点 {a.api_base}')
    parts = []
    for i, b in enumerate(beats, 1):
        tpl = random.choice(TPL)
        prompt = tpl.format(outline=b)
        try:
            seg = _chat(a.api_base, a.model, prompt, a.temperature, a.top_p,
                        a.repetition_penalty, a.no_repeat_ngram, a.max_new_tokens)
        except Exception as e:
            print(f'  !! beat{i} 调用失败: {e}')
            seg = ''
        print(f'  beat{i} 完成 {len(seg)} 字')
        parts.append(seg)
        time.sleep(0.2)
    chapter = dedupe_sentences('\n\n'.join(parts))
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write(chapter)
    print(f'\n已写出 {a.out}，共 {len(chapter)} 字')
    print('提示：拼接后仍需人工过一遍衔接与一致性；如需更稳，可对每个 beat 生成 2 版取较优。')


if __name__ == '__main__':
    main()
