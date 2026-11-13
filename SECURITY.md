# 安全策略

## 适用范围

本仓库是 CSU 校内 AI API 的客户端、连通性测试与基准工具，不包含服务端代码，
也不存储用户数据。

## 报告漏洞

请通过 GitHub 的 **Security → Report a vulnerability**（Private Security Advisory）
私下报告，不要在公开 Issue 中贴出 API Key、请求日志或可利用细节。

## API Key 处理

- `.env` 已被 `.gitignore` 忽略；仓库只保留 `.env.example` 模板。
- 测试日志会打印 Key 的前 12 个字符用于确认配置，完整 Key 不应出现在日志中。
- 若 Key 意外提交，请立即在服务端吊销并更换；仅删除提交记录不足以清除历史。
- 分享基准报告前，请确认 JSON / Markdown 中不含 Key 或私有提示词。

## 依赖安全

- Python 依赖锁定在 `python/uv.lock`。
- Go / Rust / Java 依赖分别在 `go.sum`、`Cargo.lock`、`pom.xml` 中固定版本。
- C++ 通过 CMake `FetchContent` 拉取 `nlohmann/json` 固定 tag。
- CI 仅执行离线构建与 mock 测试，不需要 API Key。
