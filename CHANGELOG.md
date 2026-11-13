# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

## [2026-11-13]

### Added

- 多维度基准 `python/benchmark.py`：15 个用例、11 个维度，支持逐用例重复、
  模型矩阵、流式/非流式、并发档位。
- 指标：TTFT、总延迟、TPOT、输出 tok/s、p50/p90/p99、推理 token、
  错误分类、并发 QPS / 输出 tok/s / backlog。
- `python/datasets/benchmark_cases.json`：连通、长文、结构化、代码、推理、
  长上下文、多轮、多语言、向量化、重排序、thinking。
- `python/bench_metrics.py`：可离线测试的指标数学与响应质量校验。
- `python/merge_reports.py`：合并限流时拆分产生的多份报告。
- `python/tests/`：内置 mock OpenAI 服务，13 个单元/端到端测试。
- `docs/benchmark-2026-11-13.md`：DeepSeek / GLM / Qwen 三模型实测报告。
- `docs/api-surface.md`：模型、字段、错误体与限流行为的实测记录。
- 仓库级文档：README 快速开始/配置/故障排查，以及 `CONTRIBUTING.md`、
  `SECURITY.md`、`CHANGELOG.md`。
- CI：Python 测试、Go / Rust / C++ / Java 构建；`Makefile` 提供本地快捷命令。

### Changed

- 模型列表更新为 `DeepSeek`、`GLM`、`Qwen`、`Embedding`、`Reranker`；
  默认模型改为 `DeepSeek`。
- `.env.example` 统一到仓库根目录；各语言加载器支持根目录回退。
- 速率限制压测增加分位数、错误分类、HTTP 状态分布、`max_backlog` 与 JSON 导出。

### Fixed

- C++：`CURLINFO_RESPONSE_CODE` 写入 `int` 导致栈破坏，Release 构建段错误。
- Python `test_requests.py`：SSE 空 `choices`（usage chunk）触发 `IndexError`。
- `fixed_qps` 压测实际串行执行的问题。

## [2026-05-12]

### Added

- Python / Java / Go / C++ / Rust 五种语言的 OpenAI 兼容连通性测试。
- OpenAI Chat Completions、Responses API、JSON mode、JSON Schema、
  LangChain / LangGraph / LangChain4j 测试。
- 速率限制压测脚本与流式对话客户端。
