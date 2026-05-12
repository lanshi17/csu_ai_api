# Rust AI API 测试

使用 Rust 测试 CSU 校内 AI API（OpenAI 兼容协议）。

## 项目结构

```
rust/
├── Cargo.toml           # 依赖管理
├── src/
│   ├── main.rs          # 测试运行入口
│   ├── config.rs        # 配置加载（.env）
│   └── http_client.rs   # reqwest HTTP 客户端
├── .env.example         # 环境变量模板
└── target/              # 编译输出
```

## 快速开始

```bash
# 1. 复制并编辑环境变量
cp .env.example .env
# 编辑 .env，填入你的 API_KEY

# 2. 运行
cargo run

# 或编译后运行
cargo build --release
./target/release/csu_ai_test
```

## 测试结果

> 测试时间: 2026-05-12 | 模型: DeepSeek-V4-Flash | Base URL: https://api.chat.csu.edu.cn/v1

| 测试项 | 结果 | 耗时 |
|--------|------|------|
| HTTP Models List | ✅ | - |
| HTTP Chat (非流式) | ✅ | 0.810s |
| HTTP Chat (流式) | ✅ | TTFT: 0.712s / 总计: 0.724s |

**全部 3/3 通过 ✅**

可用模型 (7 个): `bge-m3`, `bge-reranker-large`, `deepseek-ai/DeepSeek-V4-Flash`, `deepseek-v3`, `deepseek-v3-thinking`, `DeepSeek-V4-Flash`, `Qwen3.6-35B-A3B`

## 测试内容

| 测试项 | 说明 |
|--------|------|
| HTTP Models List | 获取可用模型列表 |
| HTTP Chat (非流式) | 同步聊天调用 |
| HTTP Chat (流式) | SSE 流式聊天（含 TTFT 指标） |

## 依赖

- **reqwest** v0.12 — HTTP 客户端（支持流式 SSE）
- **tokio** — 异步运行时
- **serde / serde_json** — JSON 序列化/反序列化
- **dotenvy** — .env 文件加载
- **futures** — 异步流处理
