# -*- coding: utf-8 -*-
"""规则式骨架生成器：把"场景正文"压缩成 85–150 字的"剧情骨架"，作为 input。

目标：input 只保留【人物 + 关键动作 + 结果/转折】，抽掉描写、道具名与感官细节，
      逼模型在 output 里自己"长细节"。

做法（纯规则，不需 LLM）：
  1. 取每段首句（网文段落多以动作/台词起头，首句信息密度最高）
  2. 丢掉纯台词段（以引号起头）与纯描写段（无人称动作词）
  3. 对保留句做轻压缩：删常见修饰副词、去引号内内容
  4. 拼接后截断到目标字数（默认 150）

用法: python scripts/auto_skeleton.py --scenes tmp/scenes_demo.json --out tmp/scenes_skel_demo.json --target 150
"""
import json, os, re, sys, io, argparse

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass

VERB = re.compile(r'(说|问|道|答|看|望|走|跑|冲|站|坐|拿|抓|掏|拔|挥|砍|打|踢|推|拉|按|开|关|'
                  r'翻|跳|躲|退|进|出|奔|扑|滚|摔|撞|抬|低|点|摇|笑|叹|皱眉|点头|摇头|转身|'
                  r'决定|发现|意识|察觉|想|记|明白|同意|拒绝|答应|袭击|攻击|击杀|救|逃|追)')
EXCL = re.compile(r'^[\s　]*[“"「]')          # 台词段
ADV = re.compile(r'(缓缓|慢慢|轻轻|悄悄|默默|微微|猛然|猛地|陡然|骤然|顿时|霎时|瞬间|'
                 r'连忙|急忙|飞快|迅速|狠狠|重重|小心翼翼的|仔仔细细的)')


def first_sentence(para):
    p = para.strip().replace('　', '')
    if not p:
        return ''
    m = re.split(r'(?<=[。！？…”」])', p)
    s = m[0] if m else p
    return s.strip()


def clean(s):
    s = re.sub(r'[“"「][^”"」]*[”"」]', '', s)     # 去引号内内容
    s = ADV.sub('', s)
    s = re.sub(r'\s+', '', s)
    return s


def skeletonize(text, target=150):
    paras = [p for p in text.split('\n') if p.strip()]
    keep = []
    for p in paras:
        if EXCL.match(p):                       # 台词段跳过
            continue
        s = clean(first_sentence(p))
        if len(s) < 6:                          # 太短，多半是语气词/残句
            continue
        if not VERB.search(s):                  # 无动作词，多半是纯描写
            continue
        if keep and s[:8] == keep[-1][:8]:      # 去重
            continue
        keep.append(s)
    out = ''.join(keep)
    if len(out) > target:
        # 优先保留前 2/3 与最后 1/3（开头与收束最要紧）
        head = out[: int(target * 0.66)]
        tail = out[-int(target * 0.3):]
        out = head + tail
        # 尽量落在句末
        k = out.rfind('。')
        if k > target * 0.6:
            out = out[: k + 1]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scenes', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--target', type=int, default=150)
    a = ap.parse_args()
    scenes = json.load(open(a.scenes, encoding='utf-8'))
    ok = 0
    for s in scenes:
        sk = skeletonize(s['text'], a.target)
        s['skeleton'] = sk
        s['skel_len'] = len(sk)
        if 85 <= len(sk) <= 160:
            ok += 1
    json.dump(scenes, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    L = sorted(s['skel_len'] for s in scenes)
    print(f'骨架已生成 -> {a.out}（{len(scenes)} 个）')
    print(f'骨架长度: min {L[0]} / p50 {L[len(L)//2]} / max {L[-1]}；落在 85–160 的 {ok}/{len(scenes)}')
    for s in scenes[:3]:
        print('=' * 70)
        print(f"{s['scene_id']}  正文{s['char_count']}字 → 骨架{s['skel_len']}字")
        print('骨架:', s['skeleton'])
        print('正文开头:', s['text'][:90].replace('\n', ' '))


if __name__ == '__main__':
    main()
