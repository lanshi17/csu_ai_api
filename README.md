# CSU AI API 客户端

中南大学校内 AI API 客户端工具，支持流式对话和速率限制压测。

## 安装

```bash
uv sync
```

## 配置

复制环境变量模板并填入你的 API Key：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API Key：

```env
API_KEY=your-api-key-here
API_BASE_URL=https://api.chat.csu.edu.cn/v1
MODEL_NAME=DeepSeek-V4-Flash
```

## 使用

### 对话模式

```bash
uv run ai_chat.py
```

支持多轮对话，输入 `/exit` 退出。

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

### 速率限制压测

```bash
# 自动探测速率限制
uv run rate_limit_test.py --mode find_limit

# 固定 QPS 压测
uv run rate_limit_test.py --mode fixed_qps --rps 5 --duration 60

# 单次并发测试
uv run rate_limit_test.py --mode single_test --requests 20 --workers 20
```

## 特性

- 流式 Markdown 渲染（rich）
- 速率限制器（滑动窗口）
- 自动重试（指数退避）
- 性能指标（TTFT、生成速率）
- 日志记录（loguru）
