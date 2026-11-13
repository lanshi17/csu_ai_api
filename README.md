# CSU AI API 客户端

中南大学校内 AI API 客户端工具，支持流式对话、多维度基准测试和速率限制压测。

## 目录结构

```
csu_ai_api/
├── python/              # Python 客户端和测试
│   ├── ai_chat.py       # 对话模式客户端
│   ├── test_api.py      # OpenAI SDK 连通性测试
│   ├── test_responses.py # OpenAI Responses API 测试
│   ├── test_anthropic.py # Anthropic SDK 测试
│   ├── test_requests.py  # requests 库 HTTP 测试
│   ├── test_langgraph.py # LangGraph + LangChain 测试
│   ├── test_json_mode.py # JSON mode + 结构化输出测试
│   ├── benchmark.py     # 多维度基准测试（指标 + Markdown/JSON 报告）
│   ├── bench_metrics.py # 分位数、吞吐与质量校验的纯函数
│   ├── merge_reports.py # 合并限流时拆分产生的多份报告
│   ├── datasets/
│   │   └── benchmark_cases.json # 11 个维度、15 个用例
│   ├── tests/           # 离线测试（内置 mock OpenAI 服务）
│   └── rate_limit_test.py # 速率限制压测
├── java/                # Java 客户端和测试
│   ├── src/main/java/com/csu/ai/
│   │   ├── TestRunner.java    # 测试入口
│   │   ├── TestOpenAI.java    # OpenAI Java SDK 测试
│   │   ├── TestResponses.java # OpenAI Responses API 测试
│   │   ├── TestHttp.java      # OkHttp HTTP 测试
│   │   └── TestLangChain4j.java # LangChain4j 测试
│   ├── .mvn/
│   │   ├── settings.xml       # Maven 阿里云镜像配置
│   │   └── wrapper/           # Maven Wrapper
│   ├── pom.xml
│   └── .env
├── go/                  # Go 客户端和测试
│   ├── main.go              # 测试入口
│   ├── config.go            # 配置加载
│   ├── openai_client.go     # OpenAI Go SDK (Chat Completions)
│   ├── responses_client.go  # OpenAI Go SDK (Responses API)
│   ├── http_client.go       # 原生 net/http 测试
│   └── go.mod / go.sum
├── cpp/                 # C++ 客户端和测试
│   ├── CMakeLists.txt       # CMake 构建配置
│   ├── main.cpp             # 测试入口
│   ├── config.h / config.cpp # 配置加载
│   └── http_client.h / http_client.cpp # libcurl HTTP 客户端
├── rust/                # Rust 客户端和测试
│   ├── Cargo.toml           # 依赖管理
│   ├── src/
│   │   ├── main.rs          # 测试入口
│   │   ├── config.rs        # 配置加载
│   │   └── http_client.rs   # reqwest HTTP 客户端
├── .env.example         # 统一环境变量模板（复制到各语言目录为 .env）
├── docs/                # 基准报告归档
│   └── benchmark-2026-11-13.md
├── logs/                # 日志目录
└── README.md
```

## Python

### 安装

```bash
cd python
uv sync
```

### 配置

```bash
cp ../.env.example .env
```

编辑 `.env` 文件，填入你的 API Key：

```env
API_KEY=your-api-key-here
API_BASE_URL=https://api.chat.csu.edu.cn/v1
MODEL_NAME=DeepSeek
REASONING_EFFORT=none   # none 关闭 thinking；default 使用服务端默认
```

基准测试、指标口径与数据集格式详见 [`python/README.md`](python/README.md)。

### 使用

#### 对话模式

```bash
uv run ai_chat.py
```

支持多轮对话，输入 `/exit` 退出。

#### 多维度基准测试

```bash
# 查看维度与用例
uv run benchmark.py --list

# 冒烟：10 个代表用例，重复 3 次，附并发档位
uv run benchmark.py --suite smoke --repeat 3 --concurrency 1,4,8

# 全量：15 个用例 × 多模型（网关限流时加 --min-interval）
uv run benchmark.py --suite full --models DeepSeek,GLM,Qwen --min-interval 6.5

# 只测单用例，对比流式/非流式
uv run benchmark.py --case zh_short_qa --repeat 5
uv run benchmark.py --case zh_short_qa --repeat 5 --no-stream
```

输出：控制台表格 + `python/results/benchmark_<时间戳>.json`（原始样本）
+ `benchmark_<时间戳>.md`（可直接粘贴进文档的 Markdown 表格）。

#### 速率限制压测

```bash
# 自动探测速率限制
uv run rate_limit_test.py --mode find_limit

# 固定 QPS 压测
uv run rate_limit_test.py --mode fixed_qps --rps 5 --duration 60

# 单次并发测试
uv run rate_limit_test.py --mode single_test --requests 20 --workers 20
```

## Java

### 运行

```bash
cd java
cp ../.env.example .env   # 编辑填入 API_KEY
mvn compile exec:java
```

## Go

### 运行

```bash
cd go
cp ../.env.example .env   # 编辑填入 API_KEY
go run .
```

## C++

### 构建 & 运行

```bash
cd cpp
cp ../.env.example .env   # 编辑填入 API_KEY
cmake -B build
cmake --build build
./build/csu_ai_test
```

## Rust

### 运行

```bash
cd rust
cp ../.env.example .env   # 编辑填入 API_KEY
cargo run
```

## 测试数据与指标

基准测试把单一“连通成功”提示词扩展为 **11 个维度、15 个用例**，定义在
`python/datasets/benchmark_cases.json`，可直接编辑或用 `--dataset` 指向自定义文件。

### 维度与用例

| 维度 | 用例 | 校验点 |
|---|---|---|
| 基础连通 `connectivity` | `zh_short_qa`、`en_short_qa` | 鉴权、路由、中英文短回答 |
| 长文生成 `long_form` | `zh_long_article` | ≥ 500 字、主题关键词命中 |
| 结构化输出 `structured` | `json_object`、`json_schema_strict` | JSON 合法、必需字段齐全 |
| 代码生成 `code` | `python_function`、`sql_query` | 代码块可被 `ast.parse`、SQL 含 SELECT/GROUP BY/ORDER BY |
| 多步推理 `reasoning` | `math_word_problem` | 多步算术最终值 371 |
| 长上下文 `long_context` | `needle_retrieval` | 约 120 段填充文本中检索暗号 |
| 多轮上下文 `multi_turn` | `multi_turn_profile` | 姓名/城市实体一致性 |
| 多语言 `multilingual` | `mixed_language`、`translate_zh2en` | 中英混排、译文且不回显中文原句 |
| 向量化 `embedding` | `embed_text` | 向量非空、批次内维度一致（当前 2560 维） |
| 重排序 `rerank` | `rerank_docs` | `/rerank` 分数降序、首位命中 |
| 深度推理 `thinking` | `math_thinking` | thinking token 数、答案正确性 |

### 当前服务面（2026-11-13 实测）

`GET /models` 返回 5 个逻辑模型：

| 模型 | 类型 | 端点 | 说明 |
|---|---|---|---|
| `DeepSeek` | chat | `POST /chat/completions` | 默认开启 thinking，`reasoning_effort=none` 可关闭 |
| `GLM` | chat | `POST /chat/completions` | 默认开启 thinking |
| `Qwen` | chat | `POST /chat/completions` | 默认开启 thinking |
| `Embedding` | embedding | `POST /embeddings` | 输出 2560 维向量 |
| `Reranker` | rerank | `POST /rerank` | Jina 风格 `results[].relevance_score` |

网关对突发请求返回 429（openresty），持续速率约 10 次/分钟。

### 指标

| 指标 | 定义 | 用途 |
|---|---|---|
| TTFT | 请求开始 → 首个内容/推理 token | 交互首字延迟 |
| 总延迟 | 请求开始 → 流结束 | 端到端耗时 |
| TPOT | `(总延迟 - TTFT) / (completion_tokens - 1)` | 单 token 解码成本 |
| 输出 tok/s | `completion_tokens / 解码时长` | 生成吞吐 |
| chars/s | `输出字符数 / 解码时长` | `usage` 缺失时的通用吞吐 |
| 推理 tok | `usage.completion_tokens_details.reasoning_tokens` | thinking 开销 |
| p50 / p90 / p99 | 多次重复的线性插值分位数 | 长尾与稳定性 |
| 成功率 | 成功请求 / 总请求 | 可用性 |
| 质量通过率 | checks 全部通过 / 成功请求 | 输出正确性 |
| 错误类别 | `rate_limit`、`auth`、`bad_request`、`server_error`、`timeout`、`connection`、`parse_error`、`unknown` | 故障定位 |
| QPS / 输出 tok/s / backlog | 并发档位的吞吐、聚合输出速率与最大积压 | 容量规划 |

> 流式请求默认携带 `stream_options.include_usage`；服务端不支持时自动回退一次，
> 此时 token 类指标记为 `null`，仅保留 chars/s 与延迟指标。基准不做自动重试，
> 失败样本按错误类别计数，避免重试掩盖真实延迟。
>
> 网关对突发请求返回 429（openresty）；实测持续速率约 **10 次/分钟**。
> 跑全量时使用 `--min-interval 6.5` 逐请求放行。

### 质量校验类型

`contains_any`、`contains_all`、`not_contains`、`regex`、`json_valid`、
`json_keys`、`min_chars`、`python_valid`（仅 AST 解析，不执行模型生成的代码）。

### 离线自测

内置 mock OpenAI 服务，验证流式采样、usage 回退、429 分类、并发探测与报告生成：

```bash
cd python
uv run python -m unittest discover -s tests -v
```

## 基准结果（2026-11-13）

> 环境：`https://api.chat.csu.edu.cn/v1`；数据集 v1.2.0；15 个用例 × 每模型重复 2 次；
> 流式、`reasoning_effort=none`、请求间隔 6.5s（约 9 次/分钟）。完整用例表与逐次样本
> 见 [`docs/benchmark-2026-11-13.md`](docs/benchmark-2026-11-13.md)。

### 维度 p50 延迟（秒）

| 维度 | DeepSeek | GLM | Qwen |
|---|---|---|---|
| 基础连通 `connectivity` | 0.364 | 0.798 | 0.135 |
| 长文生成 `long_form` | 17.010 | 22.825 | 5.193 |
| 结构化输出 `structured` | 0.785 | 0.779 | 0.404 |
| 代码生成 `code` | 0.961 | 6.180 | 0.540 |
| 多步推理 `reasoning` | 0.443 | 6.938 | 0.167 |
| 长上下文 `long_context` | 0.491 | 1.970 | 0.415 |
| 多轮上下文 `multi_turn` | 0.409 | 2.850 | 0.173 |
| 多语言 `multilingual` | 1.120 | 2.467 | 0.286 |
| 深度推理 `thinking` | 8.478 | 16.411 | 7.251 |

### 关键用例

| 用例 | DeepSeek | GLM | Qwen |
|---|---|---|---|
| 600 字长文 | 17.010s / 33.3 tok/s | 22.825s / 48.9 tok/s | 5.193s / 100.0 tok/s |
| JSON Schema strict | 0.853s / ✅ | 0.779s / ✅ | 0.404s / ✅ |
| Python 函数生成 | 1.415s / ✅ | 9.908s / ✅ | 0.666s / ✅ |
| 长上下文暗号检索 | 0.491s / ✅ | 1.970s / ✅ | 0.415s / ✅ |
| thinking 数学题 | 8.478s / 357 推理 tok / ✅ | 16.411s / 未返回 token 明细 / ✅ | 7.251s / 1006 推理 tok / ❌ |
| 向量化（2560 维） | 0.510s | 0.146s | 0.200s |
| 重排序 | 0.182s / top=0.9969 | 0.170s / top=0.9969 | 0.207s / top=0.9969 |
| 中译英 | 0.799s / ✅ | 1.792s / ❌ 回显中文 | 0.191s / ✅ |

### 结论

- Qwen 在短请求、长文与代码生成上延迟最低；长文解码约 100 tok/s。
- DeepSeek 与 GLM 的长文解码约 33–49 tok/s；GLM 在代码/推理维度延迟偏高（6–7s）。
- 开启 thinking 后，数学题延迟升至 7–16s，推理 token 约 357（DeepSeek）与 1006（Qwen）。
- Qwen 两次数学题均未答对 371；GLM 中译英回显了中文原句，质量校验未通过。
- 网关持续速率约 10 次/分钟。未加间隔的全量运行在第 25 个请求左右开始 429，后续模型全部被限流；
  加 `--min-interval 6.5` 后 3 个模型共 90 次请求 **0 失败**。

## 各语言连通性（2026-11-13）

> 测试环境：CSU 校内 API (`api.chat.csu.edu.cn/v1`)，模型 `DeepSeek`。
> 各组测试间隔约 30s，避免触发网关限流；延迟为单次观测，仅作连通性参考。

### Python

| SDK / API | 调用方式 | 连通性 | 备注 |
|---|---|---|---|
| OpenAI Chat Completions | `client.chat.completions.create()` | ✅ | 流式/非流式均支持 |
| OpenAI Responses | `client.responses.create()` | ✅ | - |
| requests (HTTP) | `requests.post("/chat/completions")` | ✅ | 非流式 0.654s；流式 TTFT 0.300s |
| LangChain-OpenAI | `ChatOpenAI.invoke()` / `.stream()` | ✅ | invoke 0.474s；TTFT 0.493s |
| LangGraph | `StateGraph` + `ChatOpenAI` | ✅ | 0.807s |
| OpenAI JSON mode | `response_format={"type": "json_object"}` | ✅ | 1.795s |
| OpenAI JSON Schema | `response_format={"type": "json_schema", ...}` | ✅ | 2.807s，strict 支持 |
| LangChain 结构化输出 | `llm.with_structured_output(Schema)` | ✅ | 1.608s，返回 Pydantic 对象 |
| LangGraph 结构化输出 | `StateGraph` + `with_structured_output` | ✅ | 5.149s |
| Anthropic Messages | `client.messages.create()` | ❌ 401 | CSU API 不支持 Anthropic 协议 |

### Java

| SDK / API | 调用方式 | 连通性 | 备注 |
|---|---|---|---|
| OpenAI SDK Models List | `client.models().list()` | ✅ | 5 个可用模型 |
| OpenAI SDK invoke() | `client.chat().completions().create()` | ✅ | 0.688s |
| OpenAI SDK stream() | `client.chat().completions().createStreaming()` | ✅ | TTFT 0.487s |
| OpenAI SDK Responses invoke() | `client.responses().create()` | ✅ | 1.139s |
| OpenAI SDK Responses stream() | `client.responses().createStreaming()` | ✅ | TTFT 0.624s |
| OkHttp Models List | `GET /models` | ✅ | 5 个可用模型 |
| OkHttp Chat (非流式) | `POST /chat/completions` | ✅ | 0.752s |
| OkHttp Chat (流式) | `POST /chat/completions` (SSE) | ✅ | TTFT 0.487s |
| LangChain4j invoke() | `ChatLanguageModel.chat()` | ✅ | 0.635s，含 15 推理 token |
| LangChain4j stream() | `StreamingChatLanguageModel.chat()` | ✅ | TTFT 0.211s |

### Go

| SDK / API | 调用方式 | 连通性 | 备注 |
|---|---|---|---|
| OpenAI SDK Models List | `client.Models.List()` | ✅ | 5 个可用模型 |
| OpenAI SDK invoke() | `client.Chat.Completions.New()` | ✅ | 0.806s |
| OpenAI SDK stream() | `client.Chat.Completions.NewStreaming()` | ✅ | TTFT 0.585s |
| OpenAI SDK Responses invoke() | `client.Responses.New()` | ✅ | 0.533s |
| OpenAI SDK Responses stream() | `client.Responses.NewStreaming()` | ✅ | TTFT 0.551s |
| HTTP Models List | `GET /models` | ✅ | 5 个可用模型 |
| HTTP Chat (非流式) | `POST /chat/completions` | ✅ | 0.487s |
| HTTP Chat (流式) | `POST /chat/completions` (SSE) | ✅ | TTFT 0.873s |

### C++

| SDK / API | 调用方式 | 连通性 | 备注 |
|---|---|---|---|
| HTTP Models List | `GET /models` (libcurl) | ✅ | 5 个可用模型 |
| HTTP Chat (非流式) | `POST /chat/completions` | ✅ | 0.722s |
| HTTP Chat (流式) | `POST /chat/completions` (SSE) | ✅ | TTFT 0.520s |

### Rust

| SDK / API | 调用方式 | 连通性 | 备注 |
|---|---|---|---|
| HTTP Models List | `GET /models` (reqwest) | ✅ | 5 个可用模型 |
| HTTP Chat (非流式) | `POST /chat/completions` | ✅ | 0.756s |
| HTTP Chat (流式) | `POST /chat/completions` (SSE) | ✅ | TTFT 0.541s |

**结论：** CSU 校内 API 仅支持 **OpenAI 兼容协议**（Chat Completions 和 Responses API 均可），不支持 Anthropic SDK 原生调用。Python、Java、Go、C++、Rust 五种语言均可正常连通。

## 特性

- 多维度基准（11 个维度、15 个用例，内置响应质量校验）
- 指标覆盖 TTFT、总延迟、TPOT、tok/s、p50/p90/p99、推理 token、错误分类与并发吞吐
- JSON + Markdown 双格式报告，Markdown 可直接粘贴引用
- 流式 Markdown 渲染（rich）
- 速率限制器（滑动窗口）
- 自动重试（指数退避）
- 性能指标（TTFT、生成速率）
- 日志记录（loguru）
