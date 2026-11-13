# CSU AI API 接口面

> 记录 2026-11-13 实测行为，Base URL：`https://api.chat.csu.edu.cn/v1`。
> 所有请求使用 `Authorization: Bearer $API_KEY`。

## 模型

`GET /models` 返回 5 个逻辑模型：

| id | 类型 | 端点 | 说明 |
|---|---|---|---|
| `DeepSeek` | chat | `POST /chat/completions` | 默认 thinking；`reasoning_effort=none` 可关闭 |
| `GLM` | chat | `POST /chat/completions` | 默认 thinking |
| `Qwen` | chat | `POST /chat/completions` | 默认 thinking |
| `Embedding` | embedding | `POST /embeddings` | 2560 维 |
| `Reranker` | rerank | `POST /rerank` | Jina 风格结果 |

模型名精确匹配，旧名（如 `DeepSeek-V4-Flash`）返回 OpenAI 风格错误：

```json
{"error":{"code":"model_not_found","message":"No available channel for model ...","type":"new_api_error"}}
```

## Chat Completions

```bash
curl -sS "$API_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "DeepSeek",
    "messages": [{"role": "user", "content": "只回复：ok"}],
    "max_tokens": 64,
    "reasoning_effort": "none"
  }'
```

实测字段：

- `reasoning_effort: "none"` 关闭 thinking；不传该字段时默认开启。
- `max_tokens` 包含推理 token。预算过小时可能返回 `content: null`、`finish_reason: "length"`。
- 非流式响应把推理放在 `choices[0].message.reasoning`（不是 `reasoning_content`）。
- `usage.completion_tokens_details.reasoning_tokens`：DeepSeek / Qwen 返回具体值，
  GLM 实测不返回该明细。
- `response_format` 支持 `{"type": "json_object"}` 与 strict `json_schema`；
  字段名不会自动翻译，需在提示词中明确要求英文 key。
- 流式（SSE）增量字段为 `delta.reasoning` 与 `delta.content`；
  末尾可能出现 `choices: []` 的 usage chunk，客户端需要跳过空 `choices`。
- 错误体是 OpenAI 风格 JSON；`429` 例外，来自 openresty 的 HTML 页面。

## Responses API

`POST /responses` 可正常调用，简单 `input` 与流式均实测通过。响应文本通过
`response.output_text` 获取。本仓库未使用工具调用/多模态字段。

## Embeddings

```bash
curl -sS "$API_BASE_URL/embeddings" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"Embedding","input":["中南大学","machine learning"]}'
```

- 返回 `data[].embedding`，实测维度 **2560**。
- `usage` 只有 `prompt_tokens` / `total_tokens`，没有 completion 计数。
- 批次内向量维度一致。

## Rerank

`POST /rerank`，Jina/Cohere 风格：

```bash
curl -sS "$API_BASE_URL/rerank" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Reranker",
    "query": "什么是机器学习？",
    "documents": ["机器学习是人工智能的分支。", "今天天气很好。"],
    "top_n": 2
  }'
```

响应：

```json
{"results":[
  {"index":0,"document":{"text":"机器学习是人工智能的分支。"},"relevance_score":0.9969},
  {"index":1,"document":{"text":"今天天气很好。"},"relevance_score":0.0}
]}
```

`results` 按 `relevance_score` 降序；`document` 是对象（字段 `text`），不是字符串。

## 速率限制

- 突发请求会被网关直接拒绝：HTTP **429**，body 为 openresty HTML。
- 实测持续速率约 **10 次/分钟**；`--min-interval 6.5`（约 9 次/分钟）可稳定运行。
- 未观察到 `Retry-After` 或 `X-RateLimit-*` 响应头；客户端应自行节流。
- 限流计数按 Key/网关维度共享，多模型并行会互相挤占额度。

## 不支持的协议

- Anthropic Messages：`POST /v1/messages` 返回 **401 invalid x-api-key**。
- 仓库只依赖 OpenAI 兼容协议（Chat Completions / Responses / Embeddings / Rerank）。
