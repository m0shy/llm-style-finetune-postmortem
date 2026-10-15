# llm-style-finetune-postmortem

A fully documented **failed experiment**: fine-tuning Qwen2.5-7B to learn web-novel prose style on a single 8GB GPU. The whole pipeline actually ran — data production, SFT/CPT, merging, GGUF quantization, llama.cpp serving, evaluation — and the conclusion is negative. That record is the point.

## TL;DR

Reading `evals/00` → `evals/11` traces a complete attribution chain: first run collapsed, pollution fixed, a sampling-noise misjudgment corrected, "AI tone" diagnosed via same-scene comparison, segmented training identified as the culprit, and finally a structural coverage-vs-style tradeoff (v18). SFT/CPT is the wrong tool for long-range, weakly-specified style; style control belongs in prompts/skills. The one successful sub-line is lenctl (five-tier length control, served via llama.cpp).

## Layout

`evals/` verdict chain and raw probe evidence · `methods/` diagnosis and method selection · `data-production/` dataset construction · `configs/` 30 training configs with an index · `scripts/` 60+ tooling · `rewrite_experiment/` blind rewrite methodology · `ops/` operations notes.

Training corpora and model weights are not published (copyright / size); dataset schema (`dataset_info.json`) is included. Docs are in Chinese; an English translation is welcome as a PR.

## License

MIT
