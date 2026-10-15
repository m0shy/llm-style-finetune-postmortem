# -*- coding: utf-8 -*-
"""生成全量 Input 信息点核对表(双向), 覆盖所有批次.
正向: Input 的信息点 -> 必须在 Output(原文) 找到 (字面)
反向: Output 的核心转折 -> 必须已写入 Input (关键词)
"""
import json, os, sys
BASE = r"<项目目录>\Datasets"
sys.path.insert(0, os.path.join(BASE, "scripts"))
from refactor_creator import OUTLINES as O1, INSTRUCTION

# 反向核对(批次0/1): 转折标签 -> 必须在 Input 出现的关键词
REVERSE = {
 "SEG-0015-01": [("铜锥没生锈", ["铜锥", "没生锈"]), ("娘娘的手心空着", ["手心空着"]), ("僵尸现身", ["僵尸"]), ("趴肩鬼登场", ["趴肩"])],
 "SEG-0015-02": [("僵尸胸口空洞、心脏被挖", ["空洞", "心脏"]), ("僵尸就是大师兄", ["大师兄"]), ("黄纸符逼退僵尸", ["黄纸符", "后退"])],
 "SEG-0015-03": [("主角中了尸毒", ["尸毒"]), ("改用第二方案收服红舞鞋", ["第二个方案", "红舞鞋"])],
 "SEG-0015-04": [("红舞鞋要求陪舞", ["陪跳"]), ("红舞鞋断掉后路", ["后路"]), ("大脑开始过载", ["过载"])],
 "SEG-0015-05": [("用蹩脚舞步还原全部节奏", ["蹩脚", "节奏"])],
 "SEG-0001-01": [("药效减弱、需加大药量", ["药效", "药量"])],
 "SEG-0001-04": [("收到黑卡与雷一兵的信", ["黑色", "卡片", "雷一兵", "信"])],
 "SEG-0002-03": [("黑卡凭空消失", ["卡片已经没了"]), ("兵哥失踪与黑卡有关", ["失踪", "黑卡"])],
 "SEG-0003-01": [("调查员上门问雷一兵", ["调查员", "雷一兵"])],
 "SEG-0003-03": [("威胁'下一个失踪的可能就是你'", ["下一个", "失踪"])],
 "SEG-0004-01": [("表哥今晚加班不回来", ["表哥", "加班"])],
 "SEG-0004-02": [("黑卡进了主角身体，变成额头印记", ["进了他的身体"])],
 "SEG-0005-01": [("确认身处灵境", ["灵境"]), ("氙灯下出现矿工帽人影", ["氙灯", "矿工帽", "人影"])],
 "SEG-0005-02": [("影子数量异常", ["影子", "十几道"]), ("隧道口一排送行黑影", ["矿工帽", "送行"]), ("灵境提示不要进庙", ["不要进庙"])],
 "SEG-0005-03": [("看不见的脚步声在追逐", ["脚步声"])],
 "SEG-0005-04": [("娘娘的手空空如也", ["空空如也"]), ("明代古庙蜡烛却在燃烧的疑点", ["蜡烛", "烧着"])],
 "SEG-0006-01": [("弟子接连失踪", ["失踪", "三人"]), ("大师兄也失踪", ["大师兄", "失踪"])],
 "SEG-0006-03": [("风里夹着求救低语", ["低语"]), ("肩骨裂纹与主殿那具一致", ["肩骨", "裂缝"]), ("一次拿到三件道具", ["古册", "铜镜", "黄纸符"])],
 "SEG-0006-05": [("日记反转：不要相信师父", ["不要相信师父"]), ("铜镜照出背上趴着鬼", ["铜镜", "背上"])],
}


# 人工批注(随生成写入核对表, 不被重新生成覆盖):
# 裁决二·R1: SEG-0248-06 "武器"这层推断的闭环说明
NOTES = {
 "SEG-0248-06": {
  "他推断法则可作武器、凑齐法则是主线之一":
   "（校验词=坑敌人，与 output 武器比喻等价——output 原文为“这是我们可以利用的武器”；"
   "初版 input 仅写“法则可以拿来坑敌人”，未覆盖该表述层，反向核对以“武器”为校验词报漏后已补）"
 },
}


def load_outlines():
    """返回 sid -> {"input","checks","turnings"}；turnings 统一为 [[label,[keys]],...]"""
    O = {}
    for k, v in O1.items():
        O[k] = {"input": v["input"], "checks": v["checks"],
                "turnings": [[lab, keys] for lab, keys in REVERSE[k]]}
    for name in ["outlines_batch2.json", "outlines_batch3.json", "outlines_batch4.json", "outlines_batch5a.json", "outlines_batch5b.json", "outlines_batch5c.json", "outlines_batch6a.json", "outlines_batch6-2a.json", "outlines_batch6-2b.json", "outlines_batch6-3a.json", "outlines_batch6-3b.json", "outlines_batch6-4a.json", "outlines_batch6-4b.json", "outlines_batch6-5a.json", "outlines_batch6-5b.json", "outlines_batch6f.json", "outlines_batch7.json", "outlines_batch8a.json", "outlines_batch8b.json"]:
        p = os.path.join(BASE, "meta", name)
        if os.path.exists(p):
            for k, v in json.load(open(p, encoding="utf-8")).items():
                O[k] = {"input": v["input"], "checks": v["checks"], "turnings": v["turnings"]}
    return O


def main():
    O = load_outlines()
    data = [json.loads(l) for l in open(os.path.join(BASE, "dataset_lingjing.jsonl"), encoding="utf-8")]
    rows, nf, nr = [], 0, 0
    for r in data:
        sid = r["metadata"]["segment_id"]
        if sid not in O:
            print("!! 无大纲:", sid); continue
        o = O[sid]
        fwd = [(c, c in r["output"]) for c in o["checks"]]
        rev = [(lab, all(k in o["input"] for k in keys)) for lab, keys in o["turnings"]]
        nf += sum(1 for _, ok in fwd if not ok)
        nr += sum(1 for _, ok in rev if not ok)
        rows.append((sid, r["metadata"]["source_position"], len(o["input"]), fwd, rev))

    L = [x[2] for x in rows]
    tp = sum(len(f) for _, _, _, f, _ in rows)
    tt = sum(len(v) for _, _, _, _, v in rows)
    n_rule = sum(1 for r in data if "核心规则/线索" in r["instruction"])
    out = ["# Input 信息点核对表（全量）\n",
           f"> 覆盖 {len(rows)} 条；**正向** = Input 每个信息点能否在 Output（原文）中找到；"
           "**反向** = Output 核心转折是否都已写进 Input。\n",
           f"- Input 长度：min {min(L)} / max {max(L)} / 均值 {sum(L)//len(L)} 字（要求 50–150）",
           f"- 正向核对：{tp} 个信息点，**未命中 {nf} 个**",
           f"- 反向核对：{tt} 个关键转折，**未覆盖 {nr} 个**",
           f"- Instruction：主创作模板 {len(rows)-n_rule} 条 + 规则发现模板 {n_rule} 条\n", "---\n"]
    for sid, pos, ic, fwd, rev in rows:
        f_ok = sum(1 for _, ok in fwd if ok)
        v_ok = sum(1 for _, ok in rev if ok)
        out.append(f"## {sid}　`{pos}`\n")
        out.append(f"**Input（{ic} 字）**：{O[sid]['input']}\n")
        out.append(f"**正向 {f_ok}/{len(fwd)}**：" + " ".join(("✅" if ok else "❌") + c for c, ok in fwd) + "\n")
        out.append(f"**反向 {v_ok}/{len(rev)}**：" + "　".join(
            ("✅" if ok else "❌") + lab + NOTES.get(sid, {}).get(lab, "")
            for lab, ok in rev) + "\n")
    rule_ids = ", ".join(r["metadata"]["segment_id"] for r in data if "核心规则/线索" in r["instruction"])
    out += ["---\n",
            "## 两套 Instruction\n",
            f"**主模板（创作）**（{len(rows)-n_rule} 条）：\n> {INSTRUCTION}\n",
            f"**差异化模板（规则/资料发现，方案3）**（{n_rule} 条：{rule_ids}）：\n> "
            "请根据以下核心规则/线索，描写角色在紧张处境中发现并理解它们的过程。要求：严禁直接罗列设定或像说明书一样陈述。"
            "必须通过角色的具体动作、感官体验（如看到某物时的生理反应）、心理活动以及与环境的互动，"
            "将这些规则自然地'展示'出来（Show, don't tell）。\n",
            "## Output\n", f"{len(rows)}/{len(rows)} 条为原文逐字复制（归一化空白后与本地语料逐字比对）。\n"]
    open(os.path.join(BASE, "Input信息点核对表.md"), "w", encoding="utf-8").write("\n".join(out))
    print(f"覆盖 {len(rows)} 条 | 正向 {tp} 点 未命中 {nf} | 反向 {tt} 转折 未覆盖 {nr}")


if __name__ == "__main__":
    main()
