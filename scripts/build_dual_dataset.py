# -*- coding: utf-8 -*-
"""双范式数据集构建器：续写式（自动·海量）+ 大纲式（既有手工数据）

为什么要"续写式"：
  「大纲→正文」样本必须人工写大纲，量级上不去（当前仅 400 条）。
  而"说人话"靠的是**大比例、高质量的原生正文语言建模**。
  续写式样本（前文→后文）**全自动可生成**，能把量级推到数千条。

来源（均为卖报小郎君，风格同源，互不冲突）：
  灵境行者（约 800 万字） + 大奉打更人（约 446 万字）

用法: python scripts/build_dual_dataset.py
输出: data_dual/dataset_continue.jsonl + data_dual/dataset_dual.jsonl
"""
import json, os, re, sys, io, random, hashlib

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass
BOOK_HOME = r'<old-lib>'
OUTDIR = r'<项目目录>\Datasets\data_dual'
os.makedirs(OUTDIR, exist_ok=True)
OUT_CONT = os.path.join(OUTDIR, 'dataset_continue.jsonl')

BOOKS = {
    '灵境行者': [
        os.path.join(BOOK_HOME, '《灵境行者》', '灵境行者(1-500章).txt'),
        os.path.join(BOOK_HOME, '《灵境行者》', '灵境行者(501-1000章).txt'),
        os.path.join(BOOK_HOME, '《灵境行者》', '灵境行者(1001-1050章).txt'),
    ],
    '大奉打更人': [
        os.path.join(BOOK_HOME, '《大奉打更人》', '大奉打更人(1-500章).txt'),
        os.path.join(BOOK_HOME, '《大奉打更人》', '大奉打更人(501-955章).txt'),
    ],
}

CH_PAT = re.compile(r'^\s*第\s*[0-9一二三四五六七八九十百千零两]+\s*[章回节]\s*.*$')
# 作者话/经营话过滤（正文里绝不该出现）
NOTE_PAT = re.compile(r'(码字|单更|双更|加更|断更|请假|上架感言|完结感言|作者的话|'
                      r'推荐票|月票|打赏|首订|求收藏|求订阅|卡文|铺垫|读者|书友|'
                      r'这一章|这章|今天|明天|本周|下一章|后面补|抱歉|嘎嘎乱杀|'
                      r'核酸|猝死|富婆文|懂得都懂|作息|字数)')

INSTR_CONT = [
    "接着下面这段文字继续往下写。保持同样的笔法与节奏，写成一段连贯的正文。",
    "以下是一段小说的开头，请顺着写下去。要求：长短句交错、画面感强，与上文无缝衔接。",
    "续写下面这段小说。文风与上文保持一致，注重感官细节与人物动作。",
    "请把下面这一段接着写下去，不要重复上文内容，直接进入后续情节。",
    "以下是小说的一段正文，请续写后面的内容。要求：节奏自然、画面清晰、对话生动。",
    "顺着下面的文字继续写。保持同一叙述视角与语气，写成一段完整的情节。",
]

CTX_MIN, CTX_MAX = 320, 520      # 前文长度
OUT_MIN, OUT_MAX = 380, 560      # 续写长度
PER_BOOK = 900                   # 每本书采样上限


def load_paras(files):
    """返回 [(chapter_title, [para,...]), ...]，并跳过整章作者话。"""
    out, cur_title, cur = [], None, []
    for f in files:
        if not os.path.isfile(f):
            print('  缺文件', f)
            continue
        from scan_noise import read_text as _rt
        with __import__('io').StringIO(_rt(f)) as fh:
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                if CH_PAT.match(s):
                    if cur_title is not None and cur:
                        out.append((cur_title, cur))
                    cur_title, cur = s, []
                else:
                    if cur_title is not None:
                        cur.append(s)
            if cur_title is not None and cur:
                out.append((cur_title, cur))
    # 跳整章作者话
    clean = []
    for t, ps in out:
        body = ''.join(ps)
        if len(body) < 400 and len(NOTE_PAT.findall(body)) >= 2:
            continue
        # 逐段剔除作者话段
        ps = [p for p in ps if not (len(p) < 220 and len(NOTE_PAT.findall(p)) >= 2)]
        if ps:
            clean.append((t, ps))
    return clean


def build_book(name, files, quota):
    chs = load_paras(files)
    total = sum(len(''.join(ps)) for _, ps in chs)
    print(f'{name}: {len(chs)} 章, {total} 字')
    rows, rnd = [], random.Random(20260911)
    seen_ctx = set()
    for title, ps in chs:
        text = '\n'.join(ps)
        # 以句为单位滑动
        pos, L = 0, len(text)
        while pos + CTX_MIN + OUT_MIN < L:
            ctx_start = max(0, pos)
            ctx_end = min(L, ctx_start + rnd.randint(CTX_MIN, CTX_MAX))
            # 对齐到句末
            k = text.rfind('。', ctx_start, ctx_end)
            if k < ctx_start + CTX_MIN - 80:
                k = text.rfind('”', ctx_start, ctx_end)
            if k <= ctx_start:
                pos += 300
                continue
            ctx = text[ctx_start:k + 1]
            out_start = k + 1
            out_end = min(L, out_start + rnd.randint(OUT_MIN, OUT_MAX))
            k2 = text.rfind('。', out_start + OUT_MIN - 120, out_end)
            if k2 <= out_start:
                pos = out_end
                continue
            out = text[out_start:k2 + 1].strip()
            pos = k2 + 1
            if len(ctx) < CTX_MIN - 60 or len(out) < OUT_MIN - 120:
                continue
            if NOTE_PAT.search(out) or NOTE_PAT.search(ctx):
                continue
            key = hashlib.md5(ctx[-80:].encode('utf-8')).hexdigest()
            if key in seen_ctx:
                continue
            seen_ctx.add(key)
            rows.append({'book': name, 'chapter': title, 'ctx': ctx, 'out': out})
    rnd.shuffle(rows)
    rows = rows[:quota]
    print(f'  -> 采样 {len(rows)} 条')
    return rows


def main():
    allrows = []
    for name, files in BOOKS.items():
        allrows += build_book(name, files, PER_BOOK)
    with open(OUT_CONT, 'w', encoding='utf-8') as f:
        for r in allrows:
            ins = INSTR_CONT[int(hashlib.md5(r['ctx'][:100].encode('utf-8')).hexdigest(), 16) % len(INSTR_CONT)]
            f.write(json.dumps({
                "instruction": ins, "input": r['ctx'], "output": r['out'],
                "metadata": {"book": r['book'], "chapter": r['chapter'], "task": "continue"}
            }, ensure_ascii=False) + '\n')
    print(f'\n续写式样本共 {len(allrows)} 条 -> {OUT_CONT}')
    from collections import Counter
    print('分布:', dict(Counter(r['book'] for r in allrows)))


if __name__ == '__main__':
    main()
