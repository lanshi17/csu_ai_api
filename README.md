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

或直接设置环境变量：

```bash
export MY_API_KEY="your-api-key"
export MY_API_BASE="https://api.chat.csu.edu.cn/v1"  # 可选
export MY_MODEL="DeepSeek-V4-Flash"                   # 可选
```

## 使用

### 对话模式

```bash
uv run csu_ai_test.py
```

支持多轮对话，输入 `/exit` 退出。

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
