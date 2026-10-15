# -*- coding: utf-8 -*-
"""批量反推细纲：场景 → v7 格式细纲（调强模型 API ✓ 逐场景处理 ✓）
用法：先配置 API_BASE 和 API_KEY，然后 python batch_reverse_outline.py [起始条] [结束条]
"""
import json
import re
import sys
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ===== API 配置（用户填 ✗）=====
API_BASE = ''   # 例如 https://xxx/v1/chat/completions
API_KEY = ''    # 例如 sk-xxx
MODEL = ''      # 例如 gpt-5.6-sol / deepseek-chat

SRC = r'<项目目录>\LLaMA-Factory\data\scenes_selected.jsonl'
OUT = r'<项目目录>\LLaMA-Factory\data\xigang_v7.jsonl'

# 少量 few-shot 示范（用户第 1 章细纲的节拍流节选 ✓ 让强模型学格式 ✓）
FEWSHOT = '''以下是一份合格的细纲示例（注意格式：标签化 ✗ 因果用箭头 ✗ 零修辞 ✗ 零完整叙事句 ✗ 台词原句保留 ✓）：

【情绪】暗流涌动——表面平静的问询，底下全是试探与攻防
【场面钥匙】止杀宫主独坐咖啡馆，编辑短信"你儿子知道我缝合他灵魂的事了"——回复炸回来："你告诉他的？！！"
【人物·状态与性格】
  张元清：目标明确——把身世疑点问透。状态：坐姿放松，问题清单在心里。性格：问话短促精准、被搪塞不恼、心里记账、用侦探小说套路理解事件。
  止杀宫主：慵懒语气说重内容、关键处保留、被将军时僵 1~2 秒再呵笑盖过、拒绝后给甜枣。
【节拍流】
  1. 略写（百字内）：张元清思考突破口是逍遥组织——因此查清它就能知道父亲和楚尚当年做了什么。但是仇人是暗夜玫瑰还是另有其人？他判断是后者——宫主当年连行者都不是。
  2. 略写（数十字）：摆着两件大事：灵体会否再撕裂、老爸留下的东西在哪。因此必须问透。
  3. 详写（四百字）：问灵体——宫主答：你妈找到了药，成为行者后反而不用担心，等级提升灵体会愈合。因此追问遗物——她摇头答不上。因此判断她在隐瞒。再问死因，她撇清推给母亲。因此列三步计划。
  4. 中景（两百字）：告辞。"我能叫你姐姐吗。""不行！"她给甜枣：需要帮助可以联系我。
  5. 详写（三百字）：星遁前抛逻辑陷阱——我见你是易容的，你怎么知道我是张元清？她用王迁的描述解释。张元清离开。
  6. 中景（两百字）：切宫主。编辑短信：你儿子知道我缝合他灵魂的事了。回复：你告诉他的？！！
【对话要点】（原句 ✓）
【信息管控】释放：… 禁止：…
【章末钩】短信炸出缝合灵魂的秘密——幕后还有人。
【扩写提示】节拍 3 四百字主力。节拍 5 三百字写出"一问将住"的爽感。全章约 1300 字。

=== 请严格按此格式，为下面的场景原文反推细纲。要求：
① 每个字段都要有 ✗ 不许省略
② 因果链用"→"连接 ✗ 每步含动机
③ 人物的口头禅/说话方式/独有反应/独有小动作必须从原文提取 ✗ 换个人就不成立 ✓
④ 零修辞 ✗ 零比喻 ✗ 零画面渲染 ✗（那些是正文的事 ✓）
⑤ 台词原句保留 ✗
⑥ 节拍标"详写/中景/略写" ✗ + 字数封顶 ✗
⑦ 末尾标"【扩写提示】" ✗ 含各节拍字数和全章总字数 ✓
⑧ 细纲字数 ≈ 正文字数 ÷ 2.5~3 ✓'''

PROMPT = FEWSHOT + '\n\n=== 场景原文 ===\n\n{scene}\n\n=== 反推细纲 ==='


def call_api(scene, retries=3):
    body = {'model': MODEL,
            'messages': [{'role': 'user', 'content': PROMPT.format(scene=scene)}],
            'max_tokens': 2000, 'temperature': 0.3}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API_BASE,
                                         data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                         headers={'Content-Type': 'application/json',
                                                  'Authorization': f'Bearer {API_KEY}'})
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read().decode('utf-8'))
            return d['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f'  ✗ 重试 {attempt+1}/{retries}: {e}')
            time.sleep(5 * (attempt + 1))
    return None


def main():
    if not API_BASE:
        print('  ✗ 请先填 API_BASE / API_KEY / MODEL ✗')
        return
    rows = [json.loads(l) for l in open(SRC, encoding='utf-8') if l.strip()]
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else len(rows)
    batch = rows[start:end]
    print(f'  处理 {start}~{end}（{len(batch)} 条）')

    done, fail = 0, 0
    with open(OUT, 'a', encoding='utf-8') as f:
        for i, r in enumerate(batch):
            scene = r['text']
            outline = call_api(scene)
            if outline is None:
                print(f'  [{start+i}] ✗ 失败跳过')
                fail += 1
                continue
            f.write(json.dumps({'book': r['book'], 'scene_id': r['scene_id'],
                                'xigang': outline, 'text': r['text']},
                               ensure_ascii=False) + '\n')
            done += 1
            if done % 20 == 0:
                print(f'  [{start+i}] ✓ 完成 {done}/{len(batch)}（失败 {fail}）')
    print(f'  ✅ 本批完成: 成功 {done} / 失败 {fail}')


if __name__ == '__main__':
    main()
