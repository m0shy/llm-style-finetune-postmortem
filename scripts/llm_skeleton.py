# -*- coding: utf-8 -*-
"""LLM 版骨架生成器（规则版已证伪：会切断句子、且不抽象具体名词）

用强模型把"场景正文"压成 120–160 字的"剧情骨架"，作为训练 input。
一次性标注成本 → 换长期本地免费创作。

对接任意 OpenAI 兼容端点（你的中转 API / 本地大模型均可）。

用法:
  set LLM_API_BASE=https://your-relay/v1
  set LLM_API_KEY=sk-xxx
  python scripts/llm_skeleton.py --scenes tmp/scenes_skel_demo.json ^
      --model gpt-4o-mini --out tmp/scenes_skel_llm.json --workers 4
"""
import json, os, re, sys, io, time, argparse, concurrent.futures as cf

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass

PROMPT = """你是小说剧情提炼器。把下面这段小说正文压缩成 120–160 字的“剧情骨架”，供写作训练使用。

硬性要求：
1. 只保留：谁（人物名）、做了什么关键动作、造成了什么结果或转折。
2. **必须把具体物件与场景抽象化**。示例：“把锈迹斑斑的菜刀换成短刀” → “换上称手的武器”；“三口陈旧的棺材、两具穿劳保服的干尸、一柄没生锈的黄铜锥” → “屋内陈设透着反常，另有一件与旧线索隐约呼应的器物格外扎眼”。
3. 删除所有环境描写、感官细节、比喻、心理旁白。
4. 人物的回忆/联想只保留“他想起某条旧线索”这一层，**不写具体内容**。
5. 按时序连贯写成 3–5 句，不分段，不加标题，不用引号。
6. 严格输出 120–160 字，**只输出骨架本身**，不要任何解释。

正文：
{text}
"""


def call(api_base, key, model, text, timeout=120):
    import requests
    url = api_base.rstrip('/') + '/chat/completions'
    body = {"model": model, "messages": [{"role": "user", "content": PROMPT.format(text=text[:4000])}],
            "temperature": 0.3, "max_tokens": 400}
    r = requests.post(url, json=body, timeout=timeout,
                      headers={"Authorization": f"Bearer {key}"} if key else {})
    r.raise_for_status()
    out = r.json()["choices"][0]["message"]["content"].strip()
    out = re.sub(r'^["“]|["”]$', '', out).replace('\n', '')
    return out


def fit(s, lo=85, hi=170):
    """把骨架限制在目标长度：超长截到句末，过短原样返回。"""
    if len(s) <= hi:
        return s
    k = s.rfind('。', 0, hi)
    return s[:k + 1] if k > lo else s[:hi]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scenes', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--api-base', default=os.environ.get('LLM_API_BASE', ''))
    ap.add_argument('--api-key', default=os.environ.get('LLM_API_KEY', ''))
    ap.add_argument('--model', default=os.environ.get('LLM_MODEL', 'gpt-4o-mini'))
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    if not a.api_base:
        print('!! 未设置 LLM_API_BASE，无法调用。示例：set LLM_API_BASE=https://your-relay/v1')
        sys.exit(2)

    scenes = json.load(open(a.scenes, encoding='utf-8'))
    if a.limit:
        scenes = scenes[: a.limit]
    done, fail = 0, 0

    def work(sc):
        try:
            return sc, fit(call(a.api_base, a.api_key, a.model, sc['text']))
        except Exception as e:
            return sc, f'__FAIL__{type(e).__name__}:{str(e)[:80]}'

    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for sc, sk in ex.map(work, scenes):
            if sk.startswith('__FAIL__'):
                fail += 1
                print(f"  !! {sc['scene_id']} {sk[8:60]}")
            else:
                sc['skeleton'] = sk
                sc['skel_len'] = len(sk)
                done += 1
                print(f"  ok {sc['scene_id']} {sc['char_count']}字 -> {len(sk)}字")
            time.sleep(0.05)

    json.dump(scenes, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    ok = sum(1 for s in scenes if s.get('skeleton'))
    print(f'\n完成 {done} / 失败 {fail} / 写出 {ok} -> {a.out}')
    if ok:
        L = sorted(s['skel_len'] for s in scenes if s.get('skeleton'))
        print(f'骨架长度: min {L[0]} / p50 {L[len(L)//2]} / max {L[-1]}')


if __name__ == '__main__':
    main()
