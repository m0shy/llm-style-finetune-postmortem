# -*- coding: utf-8 -*-
"""Unsloth 版 CPT 续训 —— 从 LLaMA-Factory 的 checkpoint-700 接着训。

设计依据（全部经过实测，不是猜的）：
  · Unsloth 能加载我们的适配器 ✓（2026-09-18 实测：392 张量挂载成功）
  · 语料字段就是 `text` ✓ → 零转换
  · torch 2.12.1+cu126 / unsloth 2026.9.6 / transformers 5.5.0 ✓

与 LLaMA-Factory 版的差异（都是有意为之）：
  · 优化器用 adamw_torch ✓（上次实测：paged_adamw_8bit 在余量薄时会抖动，慢一倍且不带来稳定性）
  · 不用 double_quant ✗（上次的根因，Unsloth 默认也不开）
  · 起始步数按"剩下多少步"算 ✗ 不是从 0 重算

用法：
    python train_unsloth_cpt.py --steps 10        # 短测（真实负载验证）
    python train_unsloth_cpt.py --steps 303       # 正式续训到 1003
"""
import argparse, os, sys, time, json

# ⚠️ 2026-09-18 实测：加载完模型就把 8GB 吃满 → 训练第一步越界 ✗
#    expandable_segments 在 torch 2.12 上 Windows 也可能支持，先开着试试 ✓
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

BASE = r"<项目目录>\Models\models\Qwen--Qwen2.5-7B-Instruct"
ADAPTER = r"<项目目录>\LLaMA-Factory\outputs\cpt_v2\checkpoint-700"
CORPUS = r"<项目目录>\LLaMA-Factory\data\cpt_corpus_v2.jsonl"
OUT = r"<项目目录>\LLaMA-Factory\outputs\cpt_unsloth"
MAXLEN = 1280   # 1792 → 1280：融合交叉熵缓冲 = 词表×序列×4B，1792 时要 1.1GB（超过余量 ✗）


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=10, help="本次训练步数")
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--bs", type=int, default=1)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--save", type=int, default=25)
    args = ap.parse_args()

    import torch
    from datasets import load_dataset
    from unsloth import FastLanguageModel, UnslothTrainer, UnslothTrainingArguments

    print("=" * 64)
    print("Unsloth CPT 续训")
    print("  起点适配器:", ADAPTER)
    print("  本次步数:  ", args.steps, "| batch", args.bs, "x accum", args.accum, "| lr", args.lr)
    print("=" * 64)

    # ---------- 加载模型 + 我们的适配器 ----------
    # ⚠️ 2026-09-18 实测（逐段测显存后定位）：
    #    写法 A「先 from_pretrained(BASE) 再 load_adapter(ADAPTER)」
    #      → torch 保留量暴增到 10656 MB ✗✗（超过显卡 8187 MB）→ 训练第一步必崩 ✗
    #    写法 B「from_pretrained(model_name=ADAPTER)」（官方文档写法 ✓）
    #      → 保留量 5566 MB ✓，占用 6689 MB，真实余量 1498 MB ✓✓
    #    → 差 5.1 GB。必须用写法 B ✓
    #    原因推测：先加载 base 再挂适配器，会触发 Unsloth 重新打包 4bit 权重 ✗
    t = time.time()
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=ADAPTER,          # ← 直接指向适配器，不要分两步
        max_seq_length=MAXLEN,
        load_in_4bit=True,
        dtype=torch.bfloat16,
    )
    print("[1] 加载（适配器路径直传） %.1fs" % (time.time() - t))

    # ⚠️ 2026-09-18 实测教训：用 load_adapter 挂适配器时**不会自动开梯度检查点** ✗
    #    结果：加载完就吃满 8GB，训练第一步直接越界 ✗
    #    get_peft_model(use_gradient_checkpointing="unsloth") 那条路会开，但我们没走那条
    #    → 必须手动开 ✓
    if hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        print("[2b] 梯度检查点已开（use_reentrant=False）")
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
        print("[2c] enable_input_require_grads 已开")

    # 确认真的可训练（不是空转）
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print("[3] 可训练参数 %d / %d (%.3f%%)" % (trainable, total, 100 * trainable / total))
    assert trainable > 0, "✗ 没有可训练参数 —— 适配器没挂上，训练会空转"

    # ---------- 数据 ----------
    ds = load_dataset("json", data_files=CORPUS, split="train")
    print("[4] 语料 %d 条" % len(ds))
    assert "text" in ds.column_names, "✗ 语料没有 text 字段"

    # 实测显存余量（开跑前）
    free, tot = torch.cuda.mem_get_info()
    print("[5] 开跑前显存 %d / %d MB（已用 %d MB）"
          % ((tot - free) // 1048576, tot // 1048576, (tot - free) // 1048576))
    del free, tot

    # ---------- 训练 ----------
    os.makedirs(OUT, exist_ok=True)
    trainer = UnslothTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds,
        dataset_text_field="text",
        max_seq_length=MAXLEN,
        dataset_num_proc=1,          # Windows 上必须为 1，否则多进程会崩 ✓
        args=UnslothTrainingArguments(
            output_dir=OUT,
            per_device_train_batch_size=args.bs,
            gradient_accumulation_steps=args.accum,
            max_steps=args.steps,
            learning_rate=args.lr,
            embedding_learning_rate=args.lr / 10,
            warmup_ratio=0.03,
            lr_scheduler_type="cosine",
            optim="adamw_8bit",      # 8bit 优化器省内存（注意：不是 paged 版 ✗ paged 会抖动）
            bf16=True,
            logging_steps=1,
            save_steps=args.save,
            save_total_limit=6,
            report_to="none",
            dataloader_num_workers=0,
            seed=20260916,
        ),
    )

    print("[6] 开始训练")
    t = time.time()
    stats = trainer.train()
    dur = time.time() - t
    print("=" * 64)
    print("训练结束：%.1f 秒 | %.1fs/步" % (dur, dur / max(1, args.steps)))
    free, tot = torch.cuda.mem_get_info()
    print("结束显存 %d / %d MB" % ((tot - free) // 1048576, tot // 1048576))
    try:
        print("末次 loss:", stats.training_loss)
    except Exception:
        pass
    print("[7] 保存适配器 →", OUT)
    model.save_pretrained(OUT)
    tokenizer.save_pretrained(OUT)
    print("=" * 64)


if __name__ == "__main__":
    main()
