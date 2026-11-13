# Python 客户端与基准测试

CSU 校内 AI API（OpenAI 兼容协议）的 Python 客户端、连通性测试、多维度基准测试
与速率限制压测。

```bash
uv sync
cp ../.env.example .env    # 填入 API_KEY
```

## 文件

| 文件 | 说明 |
|---|---|
| `ai_chat.py` | 交互式多轮对话（rich 流式 Markdown、滑动窗口限速） |
| `benchmark.py` | 多维度基准：重复采样、模型矩阵、并发探测、Markdown/JSON 报告 |
| `bench_metrics.py` | 指标数学与质量校验的纯函数（无网络依赖，可单测） |
| `datasets/benchmark_cases.json` | 11 个维度、15 个用例 |
| `merge_reports.py` | 合并多次报告（限流时分模型跑），重算分位数并输出统一报告 |
| `rate_limit_test.py` | 突发/固定 QPS 压测与阶梯式限流探测 |
| `test_*.py` | 各 SDK/协议连通性冒烟测试 |
| `tests/` | 基准工具的离线测试（内置 mock OpenAI 服务） |

## 基准测试

```bash
# 用例目录
uv run benchmark.py --list

# 冒烟：10 个代表用例，重复 3 次 + 并发档位
uv run benchmark.py --suite smoke --repeat 3 --concurrency 1,4,8

# 全量：15 个用例，多模型对比
uv run benchmark.py --suite full --models DeepSeek,GLM,Qwen

# 只跑某维度 / 某用例 / 某 tag
uv run benchmark.py --dimension code --repeat 5
uv run benchmark.py --case zh_short_qa --repeat 5 --no-stream
uv run benchmark.py --tag json_schema

# 指定数据集与输出目录
uv run benchmark.py --dataset my_cases.json --output-dir results
```

### 常用参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--suite smoke\|full` | `smoke` | `smoke` 为 10 个代表用例，`full` 为全部 15 个 |
| `--repeat` | `3` | 每个用例重复次数，用于分位数与波动 |
| `--warmup` | `1` | 每个模型预热请求数（不计入结果） |
| `--stream / --no-stream` | 流式 | 非流式没有 TTFT，用总延迟计算 tok/s |
| `--reasoning` | `none` | chat 推理强度：`none/minimal/low/medium/high/default`；`default` 不传参 |
| `--min-interval` | `0` | 请求最小间隔秒数；网关限流时用 `6.5`（约 9 次/分钟） |
| `--concurrency` | 空 | 并发档位，如 `1,4,8`；以 `zh_short_qa` 为探针 |
| `--concurrency-requests` | 并发 × 4 | 每档位请求数 |
| `--timeout` | `120` | 单请求超时（秒） |
| `--fail-on-error` | 关 | 任一请求失败则退出码 1，便于冒烟门禁 |
| `--quiet` | 关 | 不打印逐用例进度 |

### 指标口径

- **TTFT**：请求发出到首个内容 token；推理模型的 `reasoning_content` 也计入首 token。
- **TPOT**：`(总延迟 − TTFT) / (completion_tokens − 1)`，单位秒；报告里换成毫秒。
- **输出 tok/s**：`completion_tokens / 解码时长`；解码时长从 TTFT 到流结束。
- **推理 tok**：`completion_tokens_details.reasoning_tokens`；`--reasoning none` 时为 0。
  输出少于 5 token 时 tok/s 与 TPOT 记为 `-`，避免计时噪声。
- **chars/s**：字符数 / 解码时长。服务端不返回 usage 时的通用吞吐口径。
- **分位数**：对重复样本做线性插值（同 numpy 默认口径），输出 p50/p90/p99。
- **成功率 / 质量通过率**：质量只统计成功请求；无 checks 的用例（如 embedding）单独校验向量结构。
- **错误分类**：`rate_limit`、`auth`、`bad_request`、`server_error`、`timeout`、
  `connection`、`parse_error`、`unknown`。
- **并发档位**：QPS 含失败请求（容量口径）；`输出 tok/s` 只累计成功请求的 completion tokens；
  `max_backlog` 为执行队列中的峰值未完成请求数。

基准不做自动重试，避免把重试等待算进延迟。流式请求带
`stream_options.include_usage`；若服务端返回 400/422 则去掉该参数重试一次，
此时 token 指标为 `null`。

网关对突发请求返回 429（openresty HTML 页面），实测持续速率约 **10 次/分钟**。
跑全量时建议加 `--min-interval 6.5`；突发或高并发会被直接限流，并发档位本身
也应与限流策略一起解读。

### 数据集格式

```json
{
  "version": "1.1.0",
  "dimensions": {
    "code": {"name": "代码生成", "description": "..."}
  },
  "cases": [
    {
      "id": "python_function",
      "dimension": "code",
      "tags": ["python"],
      "suites": ["smoke", "full"],
      "messages": [{"role": "user", "content": "..."}],
      "max_tokens": 600,
      "temperature": 0.2,
      "response_format": {"type": "json_object"},
      "checks": [
        {"type": "python_valid"},
        {"type": "contains_all", "values": ["def normalize_phone", "return"]}
      ]
    }
  ]
}
```

- `build`：动态构造输入，目前支持 `{"type": "needle", ...}` 生成长上下文。
- `type: "embedding"`：走 `/embeddings`，需提供 `model` 与 `input`，不走 chat 流程。
- `type: "rerank"`：走 `/rerank`，需提供 `model`、`query`、`documents`，可指定 `top_index`。
- `reasoning_effort`：用例级覆盖全局 `--reasoning`；`default` 表示不传该参数。
- `checks` 支持：`contains_any`、`contains_all`、`not_contains`、`regex`、
  `json_valid`、`json_keys`、`min_chars`、`python_valid`。
  `python_valid` 只做 `ast.parse`，**不执行**模型生成的代码。

### 输出

- 控制台：用例表、维度汇总、并发扩展表。
- `results/benchmark_<时间戳>.json`：元信息、逐次样本、汇总与并发结果。
- `results/benchmark_<时间戳>.md`：同口径 Markdown 表格与错误明细，可直接引用。

限流导致需要分模型运行时，用 `merge_reports.py` 合并：

```bash
uv run merge_reports.py \
  --inputs results/deepseek/*.json results/glm/*.json results/qwen/*.json \
  --output-md results/merged.md --output-json results/merged.json
```

`results/` 已加入 `.gitignore`，需要归档时手动复制。仓库内保留了一份三模型合并报告：
[`docs/benchmark-2026-11-13.md`](../docs/benchmark-2026-11-13.md)。

## 速率限制压测

```bash
# 阶梯探测：5/10/20/30/50/100 并发，成功率低于 80% 停止
uv run rate_limit_test.py --mode find_limit --cooldown 30 --threshold 0.8

# 固定 QPS：5 req/s 持续 60s
uv run rate_limit_test.py --mode fixed_qps --rps 5 --duration 60

# 单次并发：20 请求 / 20 线程
uv run rate_limit_test.py --mode single_test --requests 20 --workers 20

# 导出 JSON（含 p50/p90/p99、错误类别、HTTP 状态分布）
uv run rate_limit_test.py --mode single_test --json-out results/rate_limit.json
```

环境变量与基准测试一致（`API_KEY`、`API_BASE_URL`、`MODEL_NAME`），同时兼容旧的
`MY_API_KEY`、`MY_API_BASE`、`MY_MODEL`。固定 QPS 模式额外报告 `max_backlog`，
用于区分「客户端排队」与「服务端限流」。

## 离线测试

```bash
uv run python -m unittest discover -s tests -v
```

测试内置 mock OpenAI 服务，覆盖流式/非流式采样、usage 回退、429 错误分类、
并发探测与报告生成，不需要真实 API Key。
