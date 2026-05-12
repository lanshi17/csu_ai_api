# C++ AI API 测试

使用 C++ 测试 CSU 校内 AI API（OpenAI 兼容协议）。

## 项目结构

```
cpp/
├── CMakeLists.txt     # CMake 构建配置
├── main.cpp           # 测试运行入口
├── config.h/cpp       # 配置加载（.env）
├── http_client.h/cpp  # libcurl HTTP 客户端
├── .env.example       # 环境变量模板
└── build/             # 编译输出
```

## 快速开始

```bash
# 1. 复制并编辑环境变量
cp .env.example .env
# 编辑 .env，填入你的 API_KEY

# 2. 构建
cmake -B build
cmake --build build

# 3. 运行
./build/csu_ai_test
```

## 测试结果

> 测试时间: 2026-05-12 | 模型: DeepSeek-V4-Flash | Base URL: https://api.chat.csu.edu.cn/v1

| 测试项 | 结果 | 耗时 |
|--------|------|------|
| HTTP Models List | ✅ | - |
| HTTP Chat (非流式) | ✅ | 5.116s |
| HTTP Chat (流式) | ✅ | TTFT: 0.755s / 总计: 0.756s |

**全部 3/3 通过 ✅**

可用模型 (7 个): `bge-m3`, `bge-reranker-large`, `deepseek-ai/DeepSeek-V4-Flash`, `deepseek-v3`, `deepseek-v3-thinking`, `DeepSeek-V4-Flash`, `Qwen3.6-35B-A3B`

## 测试内容

| 测试项 | 说明 |
|--------|------|
| HTTP Models List | 获取可用模型列表 |
| HTTP Chat (非流式) | 同步聊天调用 |
| HTTP Chat (流式) | SSE 流式聊天（含 TTFT 指标） |

## 依赖

- **libcurl** — HTTP 客户端（系统自带或 `brew install curl`）
- **nlohmann/json** — JSON 解析（CMake 自动下载 v3.11.3）
- **C++17** — 最低编译器要求
