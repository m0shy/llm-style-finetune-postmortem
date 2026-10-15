# -*- coding: utf-8 -*-
"""
灵境行者 语料切分引擎 (Phase 0-1 自动化部分)
职责: 只做「读取 + 切分 + 导出逐字原文」, 保证 original_text 零编造。
评分(Phase 2)、降级(Phase 3)、校验(Phase 4)由模型人工完成, 本脚本不做。
用法:
    python lingjing_engine.py chapters                 # 列出全部章节索引
    python lingjing_engine.py seg --chapter 15         # 切分第15章, 输出 tmp/seg_15.json
    python lingjing_engine.py seg --range 5 25         # 切分第5至25章
    python lingjing_engine.py merge --seg tmp/seg_15.json --deg tmp/deg_15.json --out dataset_x.json
"""
import os, re, json, argparse, sys

BASE = r"<old-lib>\《灵境行者》"
FILES = ["灵境行者(1-500章).txt", "灵境行者(501-1000章).txt", "灵境行者(1001-1050章).txt"]
INDEX = r"<old-lib>\<本地工具链>\lingjing_chapter_index.json"

CH_PAT = re.compile(r'^第(\d+)章\s*(.*)$')

# 二级切分标记: 出现于段首则优先在此处断开
TRANSITION = ["与此同时", "三天后", "翌日", "第二天", "次日", "另一边", "同一时间",
              "一周后", "一月后", "半年后", "多年后", "那年", "这天", "此后的",
              "回到", "时间回到", "而此刻", "而这时", "不知过了多久", "半个小时后",
              "几分钟后", "第二天一早", "清晨", "傍晚", "深夜", "夜里"]

MIN_LEN, SOFT_LEN, OPT_LEN, MAX_LEN = 200, 360, 450, 800

# 作者话过滤: 语料中夹带的"作者的话/感言/更新说明/卡文吐槽"不是小说正文, 必须排除
# 分两类标记: ① 更新与经营类 ② 创作元叙述类(谈剧情/写法/卡文)
AUTHOR_NOTE_PAT = re.compile(
    r"(码字|单更|双更|三更|加更|断更|请假|上架感言|完结感言|作者的话|"
    r"推荐票|月票|打赏|首订|起点币|狗命要紧|兄弟们|老铁|"
    r"求(收藏|订阅|推荐|月票)|(今天|明天|本周)就写了|抱歉~|"
    r"卡文|内耗|铺垫|读者|网文|书友|这一章|这章|写法|嘎嘎乱杀)")
AUTHOR_NOTE_THRESHOLD = 3


def author_note_score(text):
    return len(AUTHOR_NOTE_PAT.findall(text))


# 尾部批注: 作者附在章末的伏笔说明/创作吐槽/请假条
# 两类判定(2026-09-11 裁决一·B方案):
#   硬批注(结构性批注 / 生活经营类 / 请假口语变体): 单次命中即剪
#   创作元叙述类泛指词: 单词命中可能是正文(如"破甲的铺垫起到了效果"),
#     需【整段】命中 >= 2 才剪, 单词命中不剪
TAIL_NOTE_HARD_PAT = re.compile(
    r"(另外[，,].{0,20}(伏笔|后续|揭开|设定)|"
    r"(伏笔|设定).{0,12}(后续|以后|将来).{0,12}(揭开|说明|交代)|"
    r"后面会(写|揭开|说明|交代)|稍后(会)?(揭开|说明|交代)|"
    # 作者生活/健康类批注
    r"颈椎|游泳|码字|单更|双更|加更|断更|请假|医生(说|建议)|"
    r"兄弟们|书友们|推荐票|月票|打赏|感谢.{0,6}(盟|老板)|"
    # 成绩经营类(2026-09-11 裁决A·词表补强): 全库37处命中均在批注语境,
    #   无一位于对话/叙述内 -> 单次命中即剪
    r"追订|均订|完本|下章补|错字先更后改|pd[：:]|"
    # 请假的口语变体与补更声明
    r"请.{0,1}假|明天补|补更|明天更|稍后更)")

# 创作元叙述类(裁决清单9词 + 原词表成员"嘎嘎乱杀", 后者同为创作元叙述, 一并按>=2门槛计)
META_NOTE_PAT = re.compile(r"(铺垫|读者|这一章|这章|网文|书友|写法|卡文|内耗|嘎嘎乱杀)")
META_MIN_HITS = 2
SEP_PAT = re.compile(r"[…⋯—\-－~～\s]{2,}")

# 兼容别名: 旧脚本/扫描器引用的合并词表
TAIL_NOTE_PAT = re.compile(TAIL_NOTE_HARD_PAT.pattern + "|" + META_NOTE_PAT.pattern)


def trim_tail_note(paras):
    """从段落列表尾部剔除作者批注段与纯分隔符段. 返回 (保留的段落列表, 剔除数).

    元叙述类以整段命中数为门槛: 段内 META 命中 < 2 时, 即便段尾自然段
    含单个元叙述词也不剪(避免误删"破甲的铺垫起到了效果"这类正文).
    """
    n = 0
    meta_total = len(META_NOTE_PAT.findall("\n".join(paras)))
    while paras and len(paras) > 1:
        last = paras[-1].strip().strip("　")
        # 纯分隔符/占位段(如 "……"、"……" 后紧跟批注的残留)
        is_sep = bool(SEP_PAT.fullmatch(last))
        is_hard = bool(TAIL_NOTE_HARD_PAT.search(last))
        is_meta = bool(META_NOTE_PAT.search(last))
        if is_sep or is_hard or (is_meta and meta_total >= META_MIN_HITS):
            paras = paras[:-1]
            n += 1
        else:
            break
    return paras, n


def load_index():
    return json.load(open(INDEX, encoding="utf-8"))


def build_loc():
    loc = {}
    for f in load_index()["files"]:
        for c in f["chapters"]:
            # 同章号可能有多条索引(裸标题行 + 正文起始行), 后者才有正文:
            # 2026-09-11 修复: 由 setdefault(取首条) 改为覆盖(取末条),
            # 否则 55/198/218/255/309/332/334/349/369/393/467/502/503/593/727/749/907
            # 共 17 章会被静默跳过(0 自然段)
            loc[c["no"]] = (f["file"], c["line"], c["title"])
    return loc


def get_chapter(no, loc=None):
    """返回 (标题, 段落列表). 段落 = 去掉行尾空白后的非空行, 保留全角缩进前缀."""
    loc = loc or build_loc()
    fn, line, title = loc[no]
    txt = open(os.path.join(BASE, fn), encoding="utf-8").read().split("\n")
    out = []
    for i in range(line - 1, len(txt)):
        if i > line - 1 and CH_PAT.match(txt[i].strip()):
            break
        out.append(txt[i].rstrip())
    paras = [p for p in out if p.strip()]
    # 首段是章节标题, 单独返回
    head = paras[0].strip()
    body = paras[1:]
    return head, body


def para_len(p):
    return len(p.strip().replace("　", ""))


def split_chapter(no, loc=None):
    head, paras = get_chapter(no, loc)
    segs, cur, cur_len = [], [], 0
    def flush():
        nonlocal cur, cur_len
        if cur:
            segs.append({"text": "\n".join(cur), "paras": len(cur)})
            cur, cur_len = [], 0

    def is_boundary(p):
        """段首是否为强边界: 转场词 / 系统面板起点"""
        s = p.strip().lstrip("　")
        if s.startswith("【"):
            return True
        return any(s.startswith(t) for t in TRANSITION)

    for idx, p in enumerate(paras):
        pl = para_len(p)
        starts_b = is_boundary(p)
        # 1) 先判后加: 若加入会超上限, 且当前已够长, 先断开
        if cur and cur_len + pl > MAX_LEN and cur_len >= MIN_LEN:
            flush()
        # 2) 已达软下限(360)且本段是新边界 -> 在此断开
        elif cur and cur_len >= SOFT_LEN and starts_b:
            flush()
        cur.append(p)
        cur_len += pl
    flush()
    # 合并过短尾段
    if len(segs) >= 2 and len(segs[-1]["text"]) < MIN_LEN:
        segs[-2]["text"] += "\n" + segs[-1]["text"]
        segs[-2]["paras"] += segs[-1]["paras"]
        segs.pop()
    result = []
    for k, s in enumerate(segs, 1):
        # 先修剪尾部作者批注, 再判断整段是否为作者话(避免误杀"正文+尾部批注"的段)
        paras_in = s["text"].split("\n")
        paras_out, trimmed = trim_tail_note(paras_in)
        txt = "\n".join(paras_out)
        sc = author_note_score(txt)
        if sc >= AUTHOR_NOTE_THRESHOLD:
            print(f"  [过滤] 第{no}章 第{k}段 判定为作者话(命中{sc}) -> 已排除")
            continue
        if trimmed:
            print(f"  [修剪] 第{no}章 第{k}段 剔除尾部批注 {trimmed} 段")
        result.append({
            "segment_id": f"SEG-{no:04d}-{k:02d}",
            "chapter": no,
            "chapter_title": head.replace(f"第{no}章", "").strip(),
            "char_count": len(txt),
            "para_count": len(paras_out),
            "original_text": txt,
        })
    return result


def merge(seg_path, deg_path, out_path):
    segs = json.load(open(seg_path, encoding="utf-8"))
    deg = json.load(open(deg_path, encoding="utf-8"))
    dataset = []
    for s in segs:
        sid = s["segment_id"]
        if sid not in deg:
            continue
        d = deg[sid]
        dataset.append({
            "instruction": d.get("instruction",
                "请将以下充满AI味、逻辑生硬的文字，重写为自然流畅、具有画面感和情感张力的人类小说描写。保留所有情节信息不变。"),
            "input": d["ai_degraded_text"],
            "output": s["original_text"],
            "metadata": {
                "segment_id": sid,
                "source_position": f"第{s['chapter']}章 {s['chapter_title']}",
                "scores": d["scores"],
                "total": sum(d["scores"].values()),
                "narrative_function": d["narrative_function"],
                "degradation_rules": d["degradation_rules"],
                "char_count": s["char_count"],
            },
        })
    json.dump(dataset, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 自检: output 必须在原文中逐字命中(归一化全部空白后比对, 排除 CRLF/全角空格差异)
    raw = ""
    for fn in FILES:
        raw += open(os.path.join(BASE, fn), encoding="utf-8").read()
    norm = lambda s: re.sub(r"\s+", "", s)
    raw_n = norm(raw)
    ok, bad = 0, []
    for r in dataset:
        probe = norm(r["output"])[:80]
        if probe and probe in raw_n:
            ok += 1
        else:
            bad.append(r["metadata"]["segment_id"])
    print(f"[merge] 组装 {len(dataset)} 条 -> {out_path}")
    print(f"[自检] 逐字命中 {ok}/{len(dataset)}", ("失败:" + ",".join(bad)) if bad else "全部通过")
    return dataset


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("chapters")
    p1 = sub.add_parser("seg"); p1.add_argument("--chapter", type=int); p1.add_argument("--range", nargs=2, type=int); p1.add_argument("--out")
    p2 = sub.add_parser("merge"); p2.add_argument("--seg", required=True); p2.add_argument("--deg", required=True); p2.add_argument("--out", required=True)
    a = ap.parse_args()
    loc = build_loc()
    if a.cmd == "chapters":
        for no in sorted(loc):
            print(no, loc[no][2])
    elif a.cmd == "seg":
        chapters = [a.chapter] if a.chapter else list(range(a.range[0], a.range[1] + 1))
        allsegs = []
        for c in chapters:
            if c not in loc:
                print("跳过缺失章:", c); continue
            allsegs += split_chapter(c, loc)
        out = a.out or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "tmp", f"seg_{chapters[0]}_{chapters[-1]}.json")
        json.dump(allsegs, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"[seg] {len(chapters)}章 -> {len(allsegs)}段 -> {out}")
        for s in allsegs:
            print(f"  {s['segment_id']}  {s['char_count']}字  {s['original_text'][:24]}...")
    elif a.cmd == "merge":
        merge(a.seg, a.deg, a.out)


if __name__ == "__main__":
    main()
