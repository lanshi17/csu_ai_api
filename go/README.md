# Go AI API 测试

使用 Go 语言测试 CSU 校内 AI API（OpenAI 兼容协议）。

## 项目结构

```
go/
├── main.go              # 测试运行入口
├── config.go            # 配置加载（.env）
├── http_client.go       # 原生 net/http 实现（类似 Python requests）
├── openai_client.go     # OpenAI Go SDK Chat Completions 实现
├── responses_client.go  # OpenAI Go SDK Responses API 实现
├── go.mod               # Go 模块定义
└── go.sum               # 依赖校验
```

## 快速开始

```bash
# 1. 复制并编辑环境变量（模板在仓库根目录）
cp ../.env.example .env
# 编辑 .env，填入你的 API_KEY

# 2. 运行测试
go run .

# 或编译后运行
go build -o csu_ai_test .
./csu_ai_test
```

## 测试结果

> 测试时间: 2026-11-13 | 模型: DeepSeek | Base URL: https://api.chat.csu.edu.cn/v1

| 测试项 | 结果 | 耗时 |
|--------|------|------|
| OpenAI SDK Models List | ✅ | - |
| OpenAI SDK invoke() | ✅ | 0.806s |
| OpenAI SDK stream() | ✅ | TTFT: 0.585s / 总计: 0.615s |
| OpenAI SDK Responses invoke() | ✅ | 0.533s |
| OpenAI SDK Responses stream() | ✅ | TTFT: 0.551s / 总计: 0.608s |
| HTTP Models List | ✅ | - |
| HTTP Chat (非流式) | ✅ | 0.487s |
| HTTP Chat (流式) | ✅ | TTFT: 0.873s / 总计: 0.873s |

**全部 8/8 通过 ✅**

可用模型 (5 个): `DeepSeek`, `Embedding`, `GLM`, `Qwen`, `Reranker`

## 测试内容

| 测试项 | 说明 |
|--------|------|
| OpenAI SDK Models List | 获取可用模型列表 |
| OpenAI SDK invoke() | 同步聊天调用（Chat Completions） |
| OpenAI SDK stream() | 流式聊天调用（含 TTFT 指标） |
| OpenAI SDK Responses invoke() | 同步 Responses API 调用 |
| OpenAI SDK Responses stream() | 流式 Responses API 调用 |
| HTTP Models List | 原生 HTTP 获取模型列表 |
| HTTP Chat (非流式) | 原生 HTTP 同步聊天 |
| HTTP Chat (流式) | 原生 HTTP SSE 流式聊天 |

## 依赖

- `github.com/openai/openai-go` — OpenAI 官方 Go SDK
- `github.com/joho/godotenv` — .env 文件加载
