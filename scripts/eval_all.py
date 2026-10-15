# -*- coding: utf-8 -*-
"""一键验收 —— 把六把尺子串起来，出一张总表

为什么需要：每轮（CPT / SFT / cpt_v2 / …）都要用**完全同一套尺子**量，
手工跑六七个脚本太容易漏项或口径不一致。今天的教训就是"指标选错会看漏真问题"
（v15 原来评分最好，却在后来新增的「最长连续同构句」上最像 AI）。

六把尺子各管一件事，别混用：
  1. eval_v3.py        十探针总览（说人话/串台/漂移/古风污染/破折号/原文复读）
  2. ai_tells.py       **AI 味六项** vs 卖报原著基准 ← 用户的第一优先级
  3. compare_same_scene.py  同一场戏：作者本人怎么写 vs 模型怎么写（最干净）
  4. voice_check.py    声线区分度（几个人有台词、主角占比）
  5. typo_check.py     字级崩坏 / 异常符号混入
  6. chapter_qa.py --dup  原文查重（防背原文，CPT 后必查）

用法：
  python scripts/eval_all.py --adapter <项目目录>\\LLaMA-Factory\\outputs\\sft_on_cpt_v1 --label sft_cpt1
  python scripts/eval_all.py --label sft_cpt1 --skip-gen     # 已生成过，只重跑检查
"""
import os, sys, json, glob, argparse, subprocess

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
LF = r'<项目目录>\LLaMA-Factory'
PY = r'C:\tool\anaconda3\envs\<独立环境>\python.exe'
PY313 = r'C:\Users\<user>\<本地工具链>\binaries\python\versions\3.13.12\python.exe'


def sh(cmd, env_extra=None, timeout=None):
    env = dict(os.environ)
    env['PYTHONPATH'] = ''
    env['HF_HOME'] = os.path.join(LF, '.hfcache')
    env['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
    if env_extra:
        env.update(env_extra)
    r = subprocess.run(cmd, capture_output=True, text=True, env=env,
                       encoding='utf-8', errors='ignore', timeout=timeout)
    return (r.stdout or '') + (r.stderr or '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--adapter')
    ap.add_argument('--label', required=True)
    ap.add_argument('--skip-gen', action='store_true', help='已有产出，只重跑检查')
    ap.add_argument('--beats-n', type=int, default=3)
    a = ap.parse_args()

    outdir = os.path.join(r'<项目目录>\Datasets', 'tmp', a.label + '_out')
    print(f'===== 一键验收：{a.label} =====')
    print(f'产出目录：{outdir}\n')

    if not a.skip_gen:
        if not a.adapter:
            print('需要 --adapter（或用 --skip-gen）')
            return
        print('[1/6] 十探针生成与总览 …')
        log = os.path.join(LF, 'outputs', f'eval_{a.label}.log')
        txt = sh([PY, 'scripts/eval_v3.py', '--adapter', a.adapter], timeout=7200)
        open(log, 'w', encoding='utf-8').write(txt)
        for line in txt.split('\n'):
            if line.startswith('【'):
                print('   ', line[:110])
        # 导出每份产出，供后续检查
        rep = os.path.join(a.adapter, 'eval_report.json')
        if os.path.isfile(rep):
            os.makedirs(outdir, exist_ok=True)
            d = json.load(open(rep, encoding='utf-8'))
            for r in d:
                for i, o in enumerate(r.get('outputs_all') or [r['output']]):
                    open(os.path.join(outdir, f"{r['id']}_{i}.md"), 'w', encoding='utf-8').write(o)
        print('    产出已导出')

    if not os.path.isdir(outdir):
        print(f'找不到 {outdir}，先跑生成。')
        return
    files = glob.glob(os.path.join(outdir, '*.md'))
    print(f'\n[2/6] AI 味六项（vs 卖报原著基准）')
    print(sh([PY313, 'scripts/ai_tells.py', outdir], timeout=1800).rstrip())

    print('\n[3/6] 同场景对比（作者本人 vs 模型）')
    b1 = os.path.join(outdir, 'B1_0.md')
    if os.path.isfile(b1):
        txt = sh([PY313, 'scripts/compare_same_scene.py', '--probe-output', b1,
                  '--source', r'<old-lib>\《大奉打更人》\大奉打更人(501-955章).txt',
                  '--anchor', '宋卿作为如今司天监的扛把子'], timeout=1200)
        print('\n'.join(txt.split('\n')[3:14]))

    print('\n[4/6] 声线区分度（**只看 C1** —— 它才是自有作品那题）')
    c1 = [f for f in files if os.path.basename(f).startswith('C1')]
    if c1:
        # 必须拷到独立目录再算：直接传整个产出目录会把 B1（大奉上下文）的
        # 怀庆/宋卿也算进来，把"自有作品里的声线区分度"污染掉（踩过）
        import shutil, tempfile
        d = os.path.join(r'<项目目录>\Datasets\tmp', a.label + '_c1only')
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
        for f in c1:
            shutil.copy(f, d)
        txt = sh([PY313, 'scripts/voice_check.py', d, '--min-lines', '2'], timeout=600)
        print('\n'.join(txt.split('\n')[2:12]))

    print('\n[5/6] 字级崩坏 / 异常符号')
    for line in sh([PY313, 'scripts/typo_check.py', outdir], timeout=900).strip().split('\n')[-4:]:
        print('   ', line.strip().strip("'\","))

    print('\n[6/6] 原文查重（防背原文，CPT 后必查）')
    hits = 0
    for f in files:
        t = sh([PY313, 'scripts/chapter_qa.py', f, '--dup'], timeout=300)
        if '原文复读' in t:
            n = t.count('原文复读')
            hits += n
            if n:
                print(f'    {os.path.basename(f)}: {n} 处')
    print(f'    合计 {hits} 处' + ('  ✓ 干净' if hits == 0 else '  ⚠️ 有复读'))
    print('\n===== 验收结束 =====')


if __name__ == '__main__':
    main()
