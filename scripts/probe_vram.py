# -*- coding: utf-8 -*-
"""显存逐段测量：定位加载过程里那 7GB 到底花在哪。

背景（2026-09-18）：
  在 unsloth 环境里，加载完 base + 适配器后显存直接 8187/8187 MB ✗
  （LLaMA-Factory 环境同规模只占 ~5.8GB，还剩 2GB 余量）
  跑训练第一步就 illegal memory access ✗

  四次尝试（原样 / is_trainable / bnb 0.49.2 / 梯度检查点）都撞同一堵墙 ✗
  → 按纪律：停止盲目重试，改为逐段测量，先搞清楚前提
"""
import os, time
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

BASE = r"<项目目录>\Models\models\Qwen--Qwen2.5-7B-Instruct"
ADAPTER = r"<项目目录>\LLaMA-Factory\outputs\cpt_v2\checkpoint-700"


def mem(tag):
    import torch
    free, tot = torch.cuda.mem_get_info()
    used = (tot - free) // 1048576
    reserved = torch.cuda.memory_reserved() // 1048576
    alloc = torch.cuda.memory_allocated() // 1048576
    print("  %-28s 占用 %4d / %d MB   | torch 已分配 %4d  已保留 %4d"
          % (tag, used, tot // 1048576, alloc, reserved))


def main():
    import torch
    print("=" * 70)
    print("显存逐段测量（unsloth 环境）")
    if not torch.cuda.is_available():
        print("  ✗ CUDA 不可用")
        return
    torch.cuda.init()
    mem("① 仅初始化 CUDA")

    from unsloth import FastLanguageModel
    mem("② import unsloth 后")

    model, tok = FastLanguageModel.from_pretrained(
        model_name=BASE, max_seq_length=1792, load_in_4bit=True, dtype=torch.bfloat16)
    mem("③ 加载 base 4bit 后")

    model.load_adapter(ADAPTER, adapter_name="default", is_trainable=True)
    mem("④ 挂载适配器后")

    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
    mem("⑤ 开梯度检查点后")

    # 前向一次，看激活占多少
    try:
        ids = tok("他推门进来，面馆里只有三张桌子。" * 4, return_tensors="pt").input_ids.to("cuda")
        print("  （输入长度 %d token）" % ids.shape[1])
        mem("⑥ 前向之前")
        with torch.no_grad():
            model(input_ids=ids)
        mem("⑦ 一次前向后")
    except Exception as e:
        print("  ✗ 前向失败:", type(e).__name__, str(e)[:100])

    print("=" * 70)
    print("对照：LLaMA-Factory 环境同规模训练时约 5800 MB，还剩 2000+ MB 余量")
    print("若这里 ③ 就已经 7000+，说明是**加载方式**吃掉了显存 ✗ 而不是训练本身")


if __name__ == "__main__":
    main()
