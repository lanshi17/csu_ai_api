# CSU AI API 客户端

中南大学校内 AI API 客户端工具，支持流式对话和速率限制压测。

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
│   ├── rate_limit_test.py # 速率限制压测
│   └── .env.example     # 环境变量模板
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
│   ├── go.mod / go.sum
│   └── .env.example
├── cpp/                 # C++ 客户端和测试
│   ├── CMakeLists.txt       # CMake 构建配置
│   ├── main.cpp             # 测试入口
│   ├── config.h / config.cpp # 配置加载
│   ├── http_client.h / http_client.cpp # libcurl HTTP 客户端
│   └── .env.example
├── rust/                # Rust 客户端和测试
│   ├── Cargo.toml           # 依赖管理
│   ├── src/
│   │   ├── main.rs          # 测试入口
│   │   ├── config.rs        # 配置加载
│   │   └── http_client.rs   # reqwest HTTP 客户端
│   └── .env.example
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
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API Key：

```env
API_KEY=your-api-key-here
API_BASE_URL=https://api.chat.csu.edu.cn/v1
MODEL_NAME=DeepSeek-V4-Flash
```

### 使用

#### 对话模式

```bash
uv run ai_chat.py
```

支持多轮对话，输入 `/exit` 退出。

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
mvn compile exec:java
```

## Go

### 运行

```bash
cd go
cp .env.example .env   # 编辑填入 API_KEY
go run .
```

## C++

### 构建 & 运行

```bash
cd cpp
cp .env.example .env   # 编辑填入 API_KEY
cmake -B build
cmake --build build
./build/csu_ai_test
```

## Rust

### 运行

```bash
cd rust
cp .env.example .env   # 编辑填入 API_KEY
cargo run
```

## API 连通性测试结果

> 测试日期：2026-05-12  
> 测试环境：CSU 校内 API (`api.chat.csu.edu.cn/v1`)  
> 模型：`DeepSeek-V4-Flash`

### Python

| SDK / API | 调用方式 | 连通性 | 备注 |
|---|---|---|---|
| OpenAI Chat Completions | `client.chat.completions.create()` | ✅ | 流式/非流式均支持 |
| OpenAI Responses | `client.responses.create()` | ✅ | - |
| requests (HTTP) | `requests.post("/chat/completions")` | ✅ | 流式/非流式/模型列表 |
| LangChain-OpenAI | `ChatOpenAI.invoke()` / `.stream()` | ✅ | TTFT ~0.8s |
| LangGraph | `StateGraph` + `ChatOpenAI` | ✅ | ~0.8s |
| Anthropic Messages | `client.messages.create()` | ❌ 401 | CSU API 不支持 Anthropic 协议 |

### Java

| SDK / API | 调用方式 | 连通性 | 备注 |
|---|---|---|---|
| OpenAI SDK Models List | `client.models().list()` | ✅ | 7 个可用模型 |
| OpenAI SDK invoke() | `client.chat().completions().create()` | ✅ | ~1.3s |
| OpenAI SDK stream() | `client.chat().completions().createStreaming()` | ✅ | TTFT ~0.86s |
| OpenAI SDK Responses invoke() | `client.responses().create()` | ✅ | ~1.6s |
| OpenAI SDK Responses stream() | `client.responses().createStreaming()` | ✅ | TTFT ~0.91s |
| OkHttp Models List | `GET /models` | ✅ | 7 个可用模型 |
| OkHttp Chat (非流式) | `POST /chat/completions` | ✅ | ~0.7s |
| OkHttp Chat (流式) | `POST /chat/completions` (SSE) | ✅ | TTFT ~1.3s |
| LangChain4j invoke() | `ChatLanguageModel.chat()` | ✅ | ~1.6s |
| LangChain4j stream() | `StreamingChatLanguageModel.chat()` | ✅ | TTFT ~1.3s |

### Go

| SDK / API | 调用方式 | 连通性 | 备注 |
|---|---|---|---|
| OpenAI SDK Models List | `client.Models.List()` | ✅ | 7 个可用模型 |
| OpenAI SDK invoke() | `client.Chat.Completions.New()` | ✅ | ~0.67s |
| OpenAI SDK stream() | `client.Chat.Completions.NewStreaming()` | ✅ | TTFT ~0.71s |
| OpenAI SDK Responses invoke() | `client.Responses.New()` | ✅ | ~0.69s |
| OpenAI SDK Responses stream() | `client.Responses.NewStreaming()` | ✅ | TTFT ~0.81s |
| HTTP Models List | `GET /models` | ✅ | 7 个可用模型 |
| HTTP Chat (非流式) | `POST /chat/completions` | ✅ | ~0.59s |
| HTTP Chat (流式) | `POST /chat/completions` (SSE) | ✅ | TTFT ~0.89s |

### C++

| SDK / API | 调用方式 | 连通性 | 备注 |
|---|---|---|---|
| HTTP Models List | `GET /models` (libcurl) | ✅ | 7 个可用模型 |
| HTTP Chat (非流式) | `POST /chat/completions` | ✅ | ~5.1s |
| HTTP Chat (流式) | `POST /chat/completions` (SSE) | ✅ | TTFT ~0.76s |

### Rust

| SDK / API | 调用方式 | 连通性 | 备注 |
|---|---|---|---|
| HTTP Models List | `GET /models` (reqwest) | ✅ | 7 个可用模型 |
| HTTP Chat (非流式) | `POST /chat/completions` | ✅ | ~0.81s |
| HTTP Chat (流式) | `POST /chat/completions` (SSE) | ✅ | TTFT ~0.71s |

**结论：** CSU 校内 API 仅支持 **OpenAI 兼容协议**（Chat Completions 和 Responses API 均可），不支持 Anthropic SDK 原生调用。Python、Java、Go、C++、Rust 五种语言均可正常连通。

## 特性

- 流式 Markdown 渲染（rich）
- 速率限制器（滑动窗口）
- 自动重试（指数退避）
- 性能指标（TTFT、生成速率）
- 日志记录（loguru）
