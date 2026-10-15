# llm-style-finetune-postmortem

[![CI](https://github.com/m0shy/llm-style-finetune-postmortem/actions/workflows/ci.yml/badge.svg)](https://github.com/m0shy/llm-style-finetune-postmortem/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[简体中文](README.md) · [English](README_ENG.md)

**微调 Qwen2.5-7B 学习网文文风：一次完整记录的失败实验。**

单卡 RTX 4060 Laptop 8GB。全流程真实跑通——数据生产 → SFT/CPT → 合并 → GGUF 量化 → llama.cpp 服务化 → 验收评测——最终结论是**负面的**。这本身就是本仓库的价值：它记录了 18 个训练版本，以及每一次"感觉变好了"是如何被测量推翻的。

## TL;DR：结论链

按 `evals/` 的顺序读（00 → 11），是一条完整的归因链：

| 环节 | 结论 |
|---|---|
| 00 · v1 | 首次微调遭遇塌缩，修复后 v1 复读问题已解决（根因分析见 `methods/collapse-diagnosis.md`） |
| 03 · v6 | 专名串台（把 A 书人物写进 B 书）通过术语表注入修复 |
| 04 · v8 | 修正了一次采样噪声造成的误判——n=1 的"提升"不可信 |
| 07 · v14b | 符号化 AI 腔确诊：同场景对比下，模型学会了表面特征、丢了人味 |
| 10 · v17 | 控制变量实验证明：分段训练是风格劣化的元凶 |
| 11 · v18 | 终点：**覆盖率（3.3/6）与风格存在结构性矛盾**，二者不可兼得 |

**总结论**：在 7B + 8GB 的约束下，SFT/CPT 不是学习"文风"这类长程、弱规则目标的对口工具；风格控制应放在 prompt/skill 层与工作流层。本地小模型的正确生态位是**窄任务**——本项目唯一成功的子线是 lenctl（五档字数控制，稳定可用，量化后以 llama.cpp 服务化）。

## 目录

| 路径 | 内容 |
|---|---|
| `evals/` | **核心叙事**：v1 → v18 验收结论链与原始探针对照（先读其 README 索引） |
| `methods/` | 立项可行性、塌缩诊断、训练方法选型、指标纠偏 |
| `data-production/` | 数据集怎么造：input 骨架化、指令变体、240 条总报告 |
| `configs/` | 30 个训练配置，按 sft / cpt / multi / lenctl / merge 分组（含版本对照索引） |
| `scripts/` | 数据生产、评测、风格量化、质检工具 |
| `rewrite_experiment/` | 10 章重写盲测方法论：判分表、人味规则、DPO 偏好对生产法、泄漏扫描 |
| `ops/` | Windows TDR 训练崩溃根因、工具链手册 |
| `docs/` | 语料清洗闸设计、聚合统计指纹（纯统计值，无原文） |
| `ui/` | 章节生成台演示页 |

## 不随仓库发布的内容

- **训练语料与数据集**：版权原因。数据生产脚本与 schema（`dataset_info.json`）完整保留，可对照理解每类数据怎么来的。
- **模型权重**：体积原因。
- 逐轮中间产物与部分内部工具脚本（`evals/README.md` 有说明）。

复现指引见 `configs/README.md`。

## License

MIT

v19/v20 为目标重定向后的收尾实验，结果见 `configs/multi/` 对应配置头注释
