# configs · 训练配置索引

本目录收录各版本训练/合并配置。路径中的 `<项目目录>` 为发布时替换的占位符，复现时替换为本机对应目录即可。全部占位符的含义：

| 占位符 | 含义 |
|---|---|
| `<项目目录>` | 本地工作根目录：模型权重、LLaMA-Factory 数据/输出、大纲库等未随仓库发布的内容都在其下 |
| `<conda目录>` | conda 安装根目录，环境建在其 `envs\` 下 |
| `<独立环境>` | 训练/推理用的独立 conda 环境名 |
| `<本地工具链>` | `C:\Users\` 下的本地便携工具链目录（含 Python 3.13、llama.cpp 等） |
| `<user>` | Windows 用户名（家目录名） |
| `<old-lib>` | 早期语料素材库路径（已弃用，仅个别旧脚本保留引用） |

## multi 系列（五书合成主线，v5 → v20）

| 版本 | 配置文件 | evals 验收文档 |
|---|---|---|
| v5 | `configs/multi/qwen25-7b-multi-v5.yaml` | `evals/02-v5-regression-and-v6-fix.md` |
| v6 | `configs/multi/qwen25-7b-multi-v6.yaml` | `evals/03-v6-pollution-fixed.md`（对比段见 `evals/02`） |
| v7 | `configs/multi/qwen25-7b-multi-v7.yaml` | —（语料侧破折号清零，见配置头注释） |
| v8 | `configs/multi/qwen25-7b-multi-v8.yaml` | `evals/04-v8-corrected-uplift.md` |
| v9 | `configs/multi/qwen25-7b-multi-v9.yaml` | —（备而不发，见 `evals/04` 末尾说明） |
| v10 | `configs/multi/qwen25-7b-multi-v10.yaml` | —（多要点样本加量版） |
| v11c | `configs/multi/qwen25-7b-multi-v11c.yaml` | `evals/05-v11c-confounded-variables.md` |
| v12 | `configs/multi/qwen25-7b-multi-v12.yaml` | —（完整消化五本，见配置头注释） |
| v13 | `configs/multi/qwen25-7b-multi-v13.yaml` | `evals/06-v13-most-balanced.md` |
| v14 | `configs/multi/qwen25-7b-multi-v14.yaml` | —（rank 加倍事故版，事故记录见 v14b 配置头注释） |
| v14b | `configs/qwen25_7b_multi_v14b.yaml`（仓库根） | `evals/07-v14b-symbols-zero-ai-tone.md` |
| v15 | `configs/multi/qwen25-7b-multi-v15.yaml` | `evals/08-v15-style-win-costs.md` |
| v16 | `configs/multi/qwen25-7b-multi-v16.yaml` | `evals/09-v16-segmented-training.md` |
| v17 | `configs/multi/qwen25-7b-multi-v17.yaml` | `evals/10-v17-segmentation-culprit.md` |
| v18 | `configs/multi/qwen25-7b-multi-v18.yaml` | `evals/11-v18-structural-tradeoff.md` |
| v19 | `configs/multi/qwen25-7b-multi-v19.yaml` | — |
| v20 | `configs/multi/qwen25-7b-multi-v20.yaml` | —（AI 指纹词指令版，见配置头注释） |

每个配置头部的注释保留了该版本相对上一版的改动依据与实测数字，按版本号顺序读即是一条完整的实验决策链。

## 早期与支线配置

| 配置文件 | 说明 | evals 验收文档 |
|---|---|---|
| `configs/sft/lingjing-sft-v1.yaml` / `lingjing-sft-v2.yaml` | 最早的 v1/v2 直创范式微调 | `evals/00-v1-first-finetune.md` |
| `configs/sft/lingjing-v1.yaml` / `scene-v2.yaml` | v1 重训 / v2 混合场景级数据 | `evals/00-v1-first-finetune.md` |
| `configs/sft/dual-v3.yaml` | v3 双范式（续写 + 大纲式） | `evals/01-v3-human-judgement.md` |
| `configs/cpt/cpt-v1~v3.yaml`、`sft-on-cpt-v1/v2.yaml` | CPT 继续预训练及其上的 SFT | 暂无对应验收文档（过程见 `ops/toolchain-manual.md`） |
| `configs/lenctl/sft-lenctl-v1.yaml` | 长度可控 SFT（300/800/1500/3000/4500 五档） | 暂无对应验收文档 |
| `configs/merge/merge-sft-v2.yaml`、`merge-sft-lenctl.yaml` | LoRA 合并导出完整模型 | —（合并型配置，无训练验收） |

通用验收方法（五维盲评 + 灾难性遗忘探针）见 `evals/golden-benchmark.md`。

## 关于续训配置

各版本的续训配置与主配置仅差 `resume_from_checkpoint` 一行，故不单独保留，复现时在主配置加该字段即可。
