# CSU AI API 客户端

中南大学校内 AI API 客户端工具，支持流式对话和速率限制压测。

## 目录结构

```
csu_ai_api/
├── python/              # Python 客户端和测试
│   ├── ai_chat.py       # 对话模式客户端
│   ├── test_api.py      # OpenAI 连通性测试
│   ├── test_responses.py # OpenAI Responses API 测试
│   ├── test_anthropic.py # Anthropic SDK 测试
│   ├── rate_limit_test.py # 速率限制压测
│   └── .env.example     # 环境变量模板
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

## API 连通性测试结果

> 测试日期：2026-05-12  
> 测试环境：CSU 校内 API (`api.chat.csu.edu.cn/v1`)  
> 模型：`DeepSeek-V4-Flash`

| SDK / API | 调用方式 | 连通性 |
|---|---|---|
| OpenAI Chat Completions | `client.chat.completions.create()` | ✅ |
| OpenAI Responses | `client.responses.create()` | ✅ |
| Anthropic Messages | `client.messages.create()` | ❌ 401 |

**结论：** CSU 校内 API 仅支持 **OpenAI 兼容协议**（Chat Completions 和 Responses API 均可），不支持 Anthropic SDK 原生调用。

## 特性

- 流式 Markdown 渲染（rich）
- 速率限制器（滑动窗口）
- 自动重试（指数退避）
- 性能指标（TTFT、生成速率）
- 日志记录（loguru）
