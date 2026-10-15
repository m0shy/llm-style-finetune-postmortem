# -*- coding: utf-8 -*-
"""本地章节草稿 API —— OpenAI 兼容，给 agent / 客户端直接对话用。

它解决的"麻烦"：
  不用再手写那套长规则 instruction、专名块、分幕格式 ✗
  服务端自动拼装 ✓ 你只说一句"写第1章，大纲是……"就行 ✓

两种模式（用 model 名切换）：
  model = "自创作品-章节"  章节模式：自动套规则+专名块+按幕生成后拼接 ✓
  model = "自创作品"        原始模式：原样对话 ✓

启动：  python scripts/serve_chapter_api.py
停止：  Ctrl+C 按一次 ✓（一次开、跑完、优雅停 —— 别反复启停 ✗）

实测注意（2026-09-18）：
  · 常驻会占约 6GB 显存 ✗ → **服务运行期间不要跑训练** ✗
  · **SFT 训练之后必须重启电脑再起服务** ✗
  · 章节模式输入必须给足大纲 ✗（太短模型会自己编 ✗）
"""
import argparse, json, os, re, sys, time, uuid

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = r"<项目目录>\Models\models\Qwen--Qwen2.5-7B-Instruct"
ADAPTER = r"<项目目录>\LLaMA-Factory\outputs\sft_v2\checkpoint-150"
NAMES = r"<项目目录>\Datasets\names\自创作品_专名.txt"
BOOK = "自创作品"
MODEL_CHAP = "自创作品-章节"
MODEL_RAW = "自创作品"

INSTRUCTION = """你在续写一部番茄平台的都市暗线游戏题材商业网文。番茄口径：节奏 > 文笔，冲突 > 铺垫，落地 > 内耗。

【开篇】前 300 字出核心冲突；1000 字内出首个爽点；禁大段世界观科普，世界观只由人物行动带出。
【节奏】动作交锋、关键对白、转折揭晓放慢写细；赶路、吃饭、已交代信息一笔带过。
【心理】情绪一律外化为动作与微表情，禁直陈；内心戏不得超过半页。
【克制动笔】情绪只准用动作、对白、留白承载。严禁出现「心里一酸/心中一暖/感到/意识到/明白了/松了一口气」这类把情绪说破的词；严禁「小心翼翼地/淡淡地/深深地」这类副词；少用比喻（仿佛/宛如/犹如/像是/好像）；不要每段都摆排比与升华的架子。
【禁 AI 腔套话】严禁这些网文 AI 高频词：嘴角勾起、嘴角上扬、眼神深邃、眼中闪过一丝、微微挑眉、沉吟片刻、心中一凛、心中一沉、心中一动、心下了然、顿时、瞬间、愈发、略微、一时之间。严禁形容词堆叠却不给实指。严禁连续三句以上用同一个句式起头。
【收尾】每幕收尾留钩（对话中断/动作中断/信息不对称/金句），但严禁提前写出后续情节。
【禁令】禁圣母、禁憋屈、禁降智、禁注水、禁设定倾倒、禁反派死于话多、禁战力崩坏、禁破折号、禁"欲知后事如何"。
【归因安全】一切异常必须可归因于游戏机制/组织/能量规则，严禁写成鬼神显灵。
【禁网络符号】严禁颜文字、表情符号、特殊符号、网络缩写与英文单词；人物一律用中文口语说话。
【逐条落实】给出的每个情节要点都要落到正文，包括人物的回忆与联想，不得遗漏。
【不得增删】不得新增要点之外的转折或结局，不得编造原文没有的动作。
【禁解剖心理】不得出现自我解说式的心理分析（如"这个不重要，重要的是…"）。
【细节自生】环境、光影、声音、气味等细节须自行铺陈，不得只把要点换个说法。
【输出】只输出正文。**绝对不要输出标题、章节号、字数统计、时间戳、分隔线或任何标记**，直接以下一个自然段开始。"""

MODEL = TOK = None
NAMES_TXT = ""


def split_beats(text, n):
    paras = [p.strip() for p in re.split(r'\n\s*\n|\n', text) if p.strip()]
    if len(paras) >= n:
        size = (len(paras) + n - 1) // n
        return [''.join(paras[i:i + size]) for i in range(0, len(paras), size)][:n]
    sents = [s.strip() for s in re.split(r'(?<=[。！？；])', text) if s.strip()]
    if not sents:
        return [text.strip()] * n
    size = (len(sents) + n - 1) // n
    return [''.join(sents[i:i + size]) for i in range(0, len(sents), size)][:n]


def dedupe(text):
    seen, out = set(), []
    for para in text.split('\n'):
        p = para.strip()
        if not p:
            out.append('')
            continue
        kept = []
        for s in re.split(r'(?<=[。！？…])', p):
            k = re.sub(r'[\s　“”"\'』]', '', s)
            if len(k) >= 8 and k in seen:
                continue
            if len(k) >= 8:
                seen.add(k)
            kept.append(s)
        out.append(''.join(kept))
    return '\n'.join(out)


def load_model():
    global MODEL, TOK, NAMES_TXT
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel
    t = time.time()
    print("[1/2] 加载 tokenizer + base 4bit ...")
    TOK = AutoTokenizer.from_pretrained(BASE, trust_remote_code=True)
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                             bnb_4bit_compute_dtype=torch.bfloat16,
                             bnb_4bit_use_double_quant=False)   # 开它必越界 ✗（2026-09-16 结论）
    MODEL = AutoModelForCausalLM.from_pretrained(
        BASE, quantization_config=bnb, device_map='auto', trust_remote_code=True)
    print("[1/2] 完成 %.1fs  装载适配器 ..." % (time.time() - t))
    MODEL = PeftModel.from_pretrained(MODEL, ADAPTER)
    MODEL.eval()
    if os.path.isfile(NAMES):
        NAMES_TXT = open(NAMES, encoding='utf-8').read().strip()
    print("[2/2] ✅ 就绪（总 %.1fs）｜适配器 %s" % (time.time() - t, ADAPTER))


def gen(prompt, max_new=1100, temp=0.8, top_p=0.9, seed=20260918):
    """生成。2026-09-18 实测：动态 KV 缓存的 torch.cat 扩容会越界 ✗
       （崩在 cache_utils.py:546 的 torch.cat(value_cache...)）
       → 改用静态预分配缓存 ✓，并在前后清一次缓存碎片 ✓"""
    import torch
    torch.manual_seed(seed)
    ids = TOK.apply_chat_template([{"role": "user", "content": prompt}],
                                  add_generation_prompt=True, return_tensors="pt").to('cuda')
    # ⚠️ 2026-09-18 踩坑：max_cache_len **不能**当 generate 的参数传 ✗
    #    （会报 "model_kwargs are not used by the model" ✗）
    #    正确：只给 cache_implementation="static"，长度由它自己推 ✓
    #    另外 except 要同时抓 TypeError 和 ValueError ✗（上次只抓 TypeError 漏了 ✗）
    try:
        with torch.no_grad():
            out = MODEL.generate(ids, max_new_tokens=max_new, do_sample=(temp > 0),
                                 temperature=max(temp, 1e-5), top_p=top_p,
                                 repetition_penalty=1.15, no_repeat_ngram_size=4,
                                 pad_token_id=TOK.pad_token_id or TOK.eos_token_id,
                                 cache_implementation="static")
    except (TypeError, ValueError):
        # 老版本 transformers 不支持 static cache → 退回默认（至少不会因参数报错 ✗）
        with torch.no_grad():
            out = MODEL.generate(ids, max_new_tokens=max_new, do_sample=(temp > 0),
                                 temperature=max(temp, 1e-5), top_p=top_p,
                                 repetition_penalty=1.15, no_repeat_ngram_size=4,
                                 pad_token_id=TOK.pad_token_id or TOK.eos_token_id)
    txt = TOK.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
    del out, ids
    torch.cuda.empty_cache()
    return txt


def chapter_reply(text, beats, chapter, hints, maxtok, temp, topp):
    """章节模式：拆幕 → 逐幕生成 → 拼接去重"""
    beats_txt = split_beats(text, beats)
    segs = []
    for i, b in enumerate(beats_txt, 1):
        inp = (NAMES_TXT + "\n\n==== 本次要写 ====\n"
               + f"《{BOOK}》第{chapter}章（本次只写这一幕的第 {i}/{len(beats_txt)} 段，不要写完整章）\n"
               + f"章级大纲：{b}\n本章爽点闭环：（见章级大纲）\n")
        if hints:
            inp += f"\n==== 后文走向（仅供对齐，严禁提前写出）====\n{hints}\n"
        t0 = time.time()
        seg = gen(INSTRUCTION + "\n\n" + inp, maxtok, temp, topp, seed=20260918 + i)
        print("   [幕 %d/%d] %d 字（%.0fs）" % (i, len(beats_txt), len(seg), time.time() - t0))
        segs.append(seg)
    return dedupe('\n\n'.join(segs))


def build_app():
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI()
    # 本机网页界面要跨域访问 ✓（仅本地服务，放开无风险 ✓）
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"], allow_credentials=False)

    @app.get("/v1/models")
    def models():
        now = int(time.time())
        return {"object": "list", "data": [
            {"id": MODEL_CHAP, "object": "model", "created": now, "owned_by": "local"},
            {"id": MODEL_RAW, "object": "model", "created": now, "owned_by": "local"}]}

    @app.get("/health")
    def health():
        return {"status": "ok", "loaded": MODEL is not None, "adapter": ADAPTER}

    # ---------------- Anthropic Messages API（给 Claude Code 用 ✓）----------------
    @app.post("/v1/messages/count_tokens")
    async def count_tokens(req: Request):
        """Claude Code 会调这个 ✗ 不给会报错 —— 这里按字符粗估 ✓"""
        body = await req.json()
        n = 0
        for m in body.get("messages", []):
            c = m.get("content", "")
            if isinstance(c, list):
                c = "".join(b.get("text", "") for b in c if isinstance(b, dict))
            n += len(c or "")
        s = body.get("system", "") or ""
        if isinstance(s, list):
            s = "".join(b.get("text", "") for b in s if isinstance(b, dict))
        n += len(s)
        return JSONResponse({"input_tokens": max(1, int(n / 1.6))})   # 中文约 1.6 字/token ✓

    @app.post("/v1/messages")
    async def messages(req: Request):
        body = await req.json()
        model = body.get("model", MODEL_CHAP)
        stream = bool(body.get("stream"))
        msgs = body.get("messages", [])
        user = ""
        for m in reversed(msgs):
            if m.get("role") == "user":
                c = m.get("content", "")
                if isinstance(c, list):     # Anthropic 允许 content 是块数组
                    c = "".join(b.get("text", "") for b in c if isinstance(b, dict))
                user = c or ""
                break
        # 允许用 system 字段指定模式（Claude Code 会传 system ✓）
        sysmsg = body.get("system", "") or ""
        if isinstance(sysmsg, list):
            sysmsg = "".join(b.get("text", "") for b in sysmsg if isinstance(b, dict))
        if "原始" in sysmsg or "raw" in sysmsg.lower():
            model = MODEL_RAW
        elif "章节" in sysmsg or "chapter" in sysmsg.lower():
            model = MODEL_CHAP

        chapter = body.get("chapter") or (re.search(r'第\s*(\d+)\s*章', user).group(1)
                                          if re.search(r'第\s*(\d+)\s*章', user) else "1")
        beats = int(body.get("beats") or 2)
        hints = body.get("hints", "") or ""
        maxtok = int(body.get("max_tokens") or 1100)
        temp = float(body.get("temperature", 0.8))
        topp = float(body.get("top_p", 0.9))

        t0 = time.time()
        if model == MODEL_RAW:
            content = gen(user, maxtok, temp, topp)
        else:
            content = chapter_reply(user, beats, chapter, hints, maxtok, temp, topp)
        print("   [Anthropic] %s｜%d 字｜%.0fs" % (model, len(content), time.time() - t0))

        mid = "msg_" + uuid.uuid4().hex[:20]
        if not stream:
            return JSONResponse({
                "id": mid, "type": "message", "role": "assistant", "model": model,
                "content": [{"type": "text", "text": content}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0}})

        from fastapi.responses import StreamingResponse

        def asse():
            def ev(name, data):
                return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            yield ev("message_start", {"type": "message_start", "message": {
                "id": mid, "type": "message", "role": "assistant", "model": model,
                "content": [], "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0}}})
            yield ev("content_block_start", {"type": "content_block_start", "index": 0,
                                             "content_block": {"type": "text", "text": ""}})
            step = 40
            for i in range(0, len(content), step):
                yield ev("content_block_delta", {"type": "content_block_delta", "index": 0,
                                                 "delta": {"type": "text_delta",
                                                           "text": content[i:i + step]}})
            yield ev("content_block_stop", {"type": "content_block_stop", "index": 0})
            yield ev("message_delta", {"type": "message_delta",
                                       "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                                       "usage": {"output_tokens": 0}})
            yield ev("message_stop", {"type": "message_stop"})

        return StreamingResponse(asse(), media_type="text/event-stream")

    @app.post("/v1/chat/completions")
    async def chat(req: Request):
        body = await req.json()
        model = body.get("model", MODEL_CHAP)
        stream = bool(body.get("stream"))
        msgs = body.get("messages", [])
        user = ""
        for m in reversed(msgs):
            if m.get("role") == "user":
                user = m.get("content", "") or ""
                break
        # 支持消息里带元信息：第N章 / 分N幕 / 后文走向
        chapter = body.get("chapter") or (re.search(r'第\s*(\d+)\s*章', user).group(1)
                                          if re.search(r'第\s*(\d+)\s*章', user) else "1")
        beats = int(body.get("beats") or 2)
        hints = body.get("hints", "") or ""
        maxtok = int(body.get("max_new_tokens") or 1100)
        temp = float(body.get("temperature", 0.8))
        topp = float(body.get("top_p", 0.9))

        t0 = time.time()
        if model == MODEL_RAW:
            content = gen(user, maxtok, temp, topp)
        else:
            content = chapter_reply(user, beats, chapter, hints, maxtok, temp, topp)
        dur = time.time() - t0
        print("   [完成] %s｜%d 字｜%.0fs" % (model, len(content), dur))

        # ---- 流式（很多 agent 客户端必须要 ✗ 没有就接不上 ✗）----
        if stream:
            from fastapi.responses import StreamingResponse

            def sse():
                cid = "chatcmpl-" + uuid.uuid4().hex[:12]
                now = int(time.time())
                head = {"id": cid, "object": "chat.completion.chunk", "created": now,
                        "model": model, "choices": [{"index": 0, "delta": {"role": "assistant"},
                                                     "finish_reason": None}]}
                yield "data: " + json.dumps(head, ensure_ascii=False) + "\n\n"
                step = 40                      # 每块 40 字
                for i in range(0, len(content), step):
                    chunk = {"id": cid, "object": "chat.completion.chunk", "created": now,
                             "model": model,
                             "choices": [{"index": 0, "delta": {"content": content[i:i + step]},
                                          "finish_reason": None}]}
                    yield "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"
                tail = {"id": cid, "object": "chat.completion.chunk", "created": now,
                        "model": model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                yield "data: " + json.dumps(tail, ensure_ascii=False) + "\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(sse(), media_type="text/event-stream")

        return JSONResponse({
            "id": "chatcmpl-" + uuid.uuid4().hex[:12],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                      "total_tokens": 0},
        })

    return app


def main():
    global ADAPTER
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--adapter', default=ADAPTER)
    a = ap.parse_args()
    ADAPTER = a.adapter

    print("=" * 62)
    print("章节草稿 API（本地）")
    print("  章节模式 model = %s" % MODEL_CHAP)
    print("  原始模式 model = %s" % MODEL_RAW)
    print("  地址 http://%s:%d/v1   ｜ Ctrl+C 优雅停止" % (a.host, a.port))
    print("=" * 62)
    load_model()
    import uvicorn
    uvicorn.run(build_app(), host=a.host, port=a.port, log_level='warning')


if __name__ == "__main__":
    main()
