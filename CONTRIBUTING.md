# 贡献指南

## 环境要求

| 语言 | 版本 | 工具 |
|---|---|---|
| Python | 3.13 | [uv](https://docs.astral.sh/uv/) |
| Go | 1.22+ | `go` |
| Rust | stable | `cargo` |
| C++ | C++17 | `cmake`、`libcurl`、下载 `nlohmann/json` |
| Java | 17 | Maven（`mvn`） |

统一配置模板在仓库根目录 `.env.example`。各语言运行时读取自身目录的 `.env`；
缺失时会回退到仓库根目录 `.env`。

```bash
cp .env.example python/.env    # 或在 go/ cpp/ rust/ java/ 下执行 cp ../.env.example .env
```

## 离线验证

除基准与连通性脚本外，其余检查都不需要 API Key：

```bash
# Python：指标数学、mock OpenAI 服务、报告生成
cd python && uv sync && uv run python -m unittest discover -s tests -v

# 编译检查
cd go && go build ./...
cd rust && cargo build --release
cd cpp && cmake -B build && cmake --build build -j4
cd java && mvn -B -DskipTests compile
```

完整 CI 见 `.github/workflows/ci.yml`。

## 添加基准用例

用例定义在 `python/datasets/benchmark_cases.json`：

1. 在 `dimensions` 中声明维度（除非复用已有维度）。
2. 在 `cases` 中新增对象，至少包含：
   - `id`：唯一、稳定的英文标识；
   - `dimension`：已有维度 key；
   - `suites`：`["smoke", "full"]` 或仅 `["full"]`；
   - `messages`（chat）或 `type: embedding/rerank` 及其字段；
   - `max_tokens`、`temperature`；
   - `checks`：`contains_any`、`contains_all`、`not_contains`、`regex`、
     `json_valid`、`json_keys`、`min_chars`、`python_valid` 之一或多个。
3. 验证：

```bash
cd python
uv run benchmark.py --list
uv run benchmark.py --case <id> --repeat 1 --warmup 0
uv run python -m unittest discover -s tests -v
```

`python_valid` 只做 AST 解析，**不会执行**模型生成的代码。

## 修改指标

- 指标数学放在 `python/bench_metrics.py`，保持无网络依赖并补充单元测试。
- 报告列在 `python/benchmark.py` 的 `_case_headers` / `_case_rows` 中维护。
- 变更指标口径时同步更新 `python/README.md` 与根 README 的指标表。

## 密钥与安全

- 不要提交任何 `.env`、Key、`sk-*` 字符串或包含 Key 的日志。
- 提交前建议扫描：

```bash
git diff --cached | grep -E 'sk-[A-Za-z0-9_-]{8,}'
```

- 如需报告安全问题，请使用 GitHub Security Advisory，不要公开 Issue。

## 提交前检查

- [ ] `uv run python -m unittest discover -s tests` 通过
- [ ] 五种语言至少编译通过（改动对应语言时）
- [ ] 没有 `.env`、Key、构建产物进入暂存区
- [ ] README / CHANGELOG 与实际行为一致
- [ ] 新用例可在 `--suite smoke` 或 `--suite full` 下单独跑通

## 代码风格

- Python：4 空格、类型标注、`from __future__ import annotations`。
- Go：`gofmt`。
- Rust：`cargo fmt`。
- C++：4 空格、C++17。
- Java：4 空格、Maven 编译目标 17。
