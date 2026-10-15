# -*- coding: utf-8 -*-
"""组装《灵境行者》重写实验投喂包：每章一份可直接粘贴的提示词文件。"""
import io, os, re

BASE = r"<项目目录>/灵境重写实验"
SRC = os.path.join(BASE, "原文分章")
OUT = os.path.join(BASE, "投喂提示词")
os.makedirs(OUT, exist_ok=True)

card = io.open(os.path.join(BASE, "灵境人物卡.md"), encoding="utf-8").read()
raw = io.open(os.path.join(BASE, "灵境细纲_第1-10章.md"), encoding="utf-8").read()

# 解析细纲：# 第N章｜...｜情绪目标：...｜章末钩：...  +  【细纲】正文
sections = {}
for m in re.finditer(r"# 第(\d+)章[^\n]*?情绪目标：(.+?)。?\s*｜章末钩：(.+?)\n+\s*【细纲】\s*(.+?)(?=\n\n# 第\d+章|\Z)", raw, re.S):
    n = int(m.group(1))
    sections[n] = {"情绪": m.group(2).strip(), "钩": m.group(3).strip(), "细纲": m.group(4).strip()}

def hanzi(t):
    return len(re.findall(r"[\u4e00-\u9fff]", t))

def tail(n):
    p = os.path.join(SRC, f"ch{n:02d}.md")
    t = io.open(p, encoding="utf-8").read()
    paras = [x.strip() for x in t.split("\n") if x.strip()]
    return "\n\n".join(paras[-2:])

made = []
for n in range(1, 11):
    s = sections.get(n)
    if not s:
        print(f"!! 第{n}章细纲解析失败"); continue
    orig = io.open(os.path.join(SRC, f"ch{n:02d}.md"), encoding="utf-8").read()
    target = max(50, round(hanzi(orig) / 50) * 50)
    tailpart = (f"【上一章结尾两段】（衔接用，你的正文不要重复它们）\n{tail(n-1)}" if n > 1
                else "【上一章结尾两段】（本章是第一章，无上文）")
    prompt = (
        f"【任务】续写网文《灵境行者》第{n}章正文，约{target}字（±15%）。网文口语，对话多，段落短。"
        f"直接写正文：不要标题、不要任何解说或小结。\n\n"
        f"【人物卡】（写正文时按此卡演人物：性格、口癖、人物之间的感情，一律以卡为准）\n{card.strip()}\n\n"
        f"{tailpart}\n\n"
        f"【本章细纲】（剧情按此执行，不要漏节拍，也不要自行加戏）\n{s['细纲']}\n\n"
        f"【本章情绪目标】{s['情绪']}\n"
        f"【章末必须收在这个钩上】{s['钩']}\n"
    )
    fn = os.path.join(OUT, f"ch{n:02d}_提示词.txt")
    io.open(fn, "w", encoding="utf-8", newline="\n").write(prompt)
    made.append((n, target, len(prompt)))

for n, tgt, plen in made:
    print(f"ch{n:02d}: 目标{tgt}字，提示词{plen}字符")
print(f"共生成 {len(made)} 份 -> {OUT}")
