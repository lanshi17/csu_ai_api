#!/usr/bin/env python
# coding=utf-8
"""bench_metrics 与 benchmark 的离线测试。

用本地 mock OpenAI 服务验证：流式/非流式采样、usage 回退、错误分类、
并发探测、JSON/Markdown 报告生成。无需真实 API Key。
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bench_metrics as bm  # noqa: E402
import benchmark  # noqa: E402
import merge_reports  # noqa: E402

# ========== Mock OpenAI 服务 ==========

JSON_CONTENT = json.dumps(
    {
        "name": "张三",
        "age": 25,
        "email": "zhangsan@example.com",
        "hobbies": ["读书", "游泳"],
    },
    ensure_ascii=False,
)

ANSWER_TEXT = (
    "连通成功。CONNECTED。\n"
    "API 是一组接口规范。What is an API? It defines how software components communicate.\n"
    "人工智能正在改变医疗行业。\n"
    "暗号是 PURPLE-7391。\n"
    "最终答案是 371。\n"
    "林川在长沙工作。\n"
    "Machine learning models require large amounts of high-quality training data.\n"
    "```python\n"
    "def normalize_phone(number: str) -> str:\n"
    "    digits = number.replace(' ', '').replace('-', '')\n"
    "    return digits.removeprefix('+86')\n"
    "```\n"
    "SELECT user_id, COUNT(*) AS cnt FROM orders GROUP BY user_id ORDER BY cnt DESC;\n"
    + "人工智能与医疗的结合提升了诊断效率。" * 60
)


def _sse_chunks(content: str, model: str, thinking: bool = False) -> list[dict]:
    events = []
    if thinking:
        events.append(
            {
                "id": "chatcmpl-mock",
                "object": "chat.completion.chunk",
                "created": 1700000000,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "reasoning": "先分析题目，再计算。"},
                        "finish_reason": None,
                    }
                ],
            }
        )
    pieces = [content[i : i + 120] for i in range(0, len(content), 120)]
    events.extend(
        {
            "id": "chatcmpl-mock",
            "object": "chat.completion.chunk",
            "created": 1700000000,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": piece},
                    "finish_reason": None,
                }
            ],
        }
        for piece in pieces
    )
    events.append(
        {
            "id": "chatcmpl-mock",
            "object": "chat.completion.chunk",
            "created": 1700000000,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
    )
    return events


class MockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):  # noqa: A003 - 静默测试日志
        pass

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler 接口
        if self.path == "/v1/models":
            self._json(200, {"object": "list", "data": [{"id": "mock-model", "object": "model"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler 接口
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        model = body.get("model", "mock-model")

        if self.path == "/v1/embeddings":
            inputs = body.get("input") or []
            if isinstance(inputs, str):
                inputs = [inputs]
            self._json(
                200,
                {
                    "object": "list",
                    "model": model,
                    "data": [
                        {"object": "embedding", "index": i, "embedding": [0.1 + i * 0.01] * 8}
                        for i in range(len(inputs))
                    ],
                    "usage": {"prompt_tokens": 4, "total_tokens": 4},
                },
            )
            return

        if self.path == "/v1/rerank":
            docs = body.get("documents") or []
            results = [
                {
                    "index": i,
                    "document": {"text": doc},
                    "relevance_score": round(0.99 - 0.1 * i, 4),
                }
                for i, doc in enumerate(docs)
            ]
            results.sort(key=lambda item: item["relevance_score"], reverse=True)
            self._json(200, {"results": results})
            return

        if self.path != "/v1/chat/completions":
            self._json(404, {"error": {"message": "not found"}})
            return

        if model == "rate-limited-model":
            self._json(429, {"error": {"message": "rate limit exceeded", "type": "rate_limit_error"}})
            return

        content = JSON_CONTENT if body.get("response_format") else ANSWER_TEXT
        thinking = "reasoning_effort" not in body
        usage = {"prompt_tokens": 10, "completion_tokens": 100, "total_tokens": 110}
        if thinking:
            usage["completion_tokens_details"] = {"reasoning_tokens": 12}

        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            events = _sse_chunks(content, model, thinking)
            if model != "no-usage-model":
                events.append(
                    {
                        "id": "chatcmpl-mock",
                        "object": "chat.completion.chunk",
                        "created": 1700000000,
                        "model": model,
                        "choices": [],
                        "usage": usage,
                    }
                )
            for event in events:
                line = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        message = {"role": "assistant", "content": content}
        if thinking:
            message["reasoning"] = "先分析题目，再进行计算。"
        self._json(
            200,
            {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": 1700000000,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "stop",
                    }
                ],
                "usage": usage,
            },
        )


class MockServer:
    def __init__(self) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address
        return f"http://{host}:{port}/v1"

    def __enter__(self) -> "MockServer":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


# ========== 纯函数测试 ==========

class TestMetrics(unittest.TestCase):
    def test_percentile(self) -> None:
        data = [1, 2, 3, 4]
        self.assertEqual(bm.percentile(data, 0), 1)
        self.assertEqual(bm.percentile(data, 50), 2.5)
        self.assertAlmostEqual(bm.percentile(data, 90), 3.7)
        self.assertAlmostEqual(bm.percentile(data, 99), 3.97)
        self.assertEqual(bm.percentile([7], 90), 7)
        self.assertIsNone(bm.percentile([], 50))
        with self.assertRaises(ValueError):
            bm.percentile(data, 101)

    def test_summarize(self) -> None:
        self.assertEqual(bm.summarize([])["n"], 0)
        single = bm.summarize([1.0])
        self.assertEqual(single["mean"], 1.0)
        self.assertEqual(single["std"], 0.0)
        self.assertIsNone(single["ci95"])

        stats = bm.summarize([1, 2, 3, 4])
        self.assertEqual(stats["n"], 4)
        self.assertAlmostEqual(stats["mean"], 2.5)
        self.assertAlmostEqual(stats["p90"], 3.7)
        self.assertAlmostEqual(stats["ci95"], 1.96 * math.sqrt(5 / 3) / 2)

    def test_classify_error(self) -> None:
        class RateLimitError(Exception):
            status_code = 429

        class AuthenticationError(Exception):
            status_code = 401

        class APITimeoutError(Exception):
            pass

        class APIConnectionError(Exception):
            pass

        class InternalServerError(Exception):
            status_code = 500

        class BadRequestError(Exception):
            status_code = 400

        self.assertEqual(bm.classify_error(RateLimitError()), "rate_limit")
        self.assertEqual(bm.classify_error(AuthenticationError()), "auth")
        self.assertEqual(bm.classify_error(APITimeoutError()), "timeout")
        self.assertEqual(bm.classify_error(APIConnectionError()), "connection")
        self.assertEqual(bm.classify_error(InternalServerError()), "server_error")
        self.assertEqual(bm.classify_error(BadRequestError()), "bad_request")
        self.assertEqual(bm.classify_error(json.JSONDecodeError("x", "", 0)), "parse_error")
        self.assertEqual(bm.classify_error(ValueError("x")), "unknown")

    def test_checks(self) -> None:
        text = "Hello 世界"
        self.assertEqual(bm.run_checks(text, [{"type": "contains_any", "values": ["hello"]}]), (True, "ok"))
        self.assertEqual(bm.run_checks(text, [{"type": "contains_all", "values": ["HELLO", "世界"]}]), (True, "ok"))
        self.assertEqual(bm.run_checks(text, [{"type": "not_contains", "values": ["missing"]}]), (True, "ok"))
        self.assertEqual(bm.run_checks(text, [{"type": "regex", "pattern": "[\\u4e00-\\u9fa5]"}] ), (True, "ok"))
        self.assertEqual(bm.run_checks(text, [{"type": "min_chars", "value": 3}]), (True, "ok"))
        self.assertEqual(bm.run_checks(text, [{"type": "json_valid"}])[0], False)
        self.assertEqual(bm.run_checks("[1, 2]", [{"type": "json_valid"}])[0], True)
        self.assertEqual(
            bm.run_checks('{"a": 1}', [{"type": "json_keys", "keys": ["a"]}])[0], True
        )
        self.assertEqual(
            bm.run_checks(
                "```python\ndef f():\n    return 1\n```", [{"type": "python_valid"}]
            )[0],
            True,
        )
        self.assertEqual(
            bm.run_checks("```python\ndef f(:\n```", [{"type": "python_valid"}])[0], False
        )
        with self.assertRaises(ValueError):
            bm.run_checks(text, [{"type": "nope"}])

    def test_summarize_samples(self) -> None:
        samples = [
            bm.Sample("c", "d", "m", True, True, latency=1.0, ttft=0.2,
                      completion_tokens=10, tps=20, quality=True),
            bm.Sample("c", "d", "m", True, True, latency=2.0, ttft=0.4,
                      completion_tokens=20, tps=10, quality=False),
            bm.Sample("c", "d", "m", False, True, latency=0.5,
                      error="RateLimitError", error_class="rate_limit"),
        ]
        summary = bm.summarize_samples(samples)
        self.assertAlmostEqual(summary.success_rate, 2 / 3)
        self.assertEqual(summary.quality_rate, 0.5)
        self.assertEqual(summary.errors, {"rate_limit": 1})
        self.assertEqual(summary.latency["n"], 2)
        self.assertAlmostEqual(summary.ttft["p50"], 0.3)


# ========== 端到端测试 ==========

class TestBenchmarkE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = MockServer().__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.__exit__(None, None, None)

    def _run(
        self, *extra: str, suite: str = "smoke", model: str = "mock-model"
    ) -> tuple[int, Path]:
        tmp = Path(tempfile.mkdtemp(prefix="bench-e2e-"))
        argv = [
            "--base-url", self.server.base_url,
            "--api-key", "test-key",
            "--models", model,
            "--suite", suite,
            "--repeat", "1",
            "--warmup", "0",
            "--output-dir", str(tmp),
            *extra,
        ]
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = benchmark.main(argv)
        reports = sorted(tmp.glob("benchmark_*.json"))
        self.assertTrue(reports, out.getvalue())
        return code, reports[-1]

    def test_smoke_stream(self) -> None:
        code, json_path = self._run()
        self.assertEqual(code, 0)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(data["meta"]["dataset_version"], "1.2.0")
        self.assertTrue(data["summaries"])
        for summary in data["summaries"]:
            for sample in summary["samples"]:
                self.assertTrue(sample["ok"], sample)
        chat = [
            s
            for summary in data["summaries"]
            if summary["case_id"] == "zh_short_qa"
            for s in summary["samples"]
        ][0]
        self.assertTrue(chat["stream"])
        self.assertEqual(chat["completion_tokens"], 100)
        self.assertGreater(chat["ttft"], 0)
        self.assertGreater(chat["chunks"], 1)
        self.assertIsNotNone(chat["tps"])
        self.assertTrue(chat["quality"])
        embedding = [
            s
            for summary in data["summaries"]
            if summary["case_id"] == "embed_text"
            for s in summary["samples"]
        ][0]
        self.assertTrue(embedding["ok"])
        self.assertEqual(embedding["embedding_dim"], 8)
        self.assertTrue(embedding["quality"])

        md = json_path.with_suffix(".md").read_text(encoding="utf-8")
        self.assertIn("用例结果", md)
        self.assertIn("维度汇总", md)
        self.assertIn("zh_short_qa", md)

    def test_usage_fallback(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="bench-nousage-"))
        argv = [
            "--base-url", self.server.base_url,
            "--api-key", "test-key",
            "--models", "no-usage-model",
            "--case", "zh_short_qa",
            "--repeat", "1",
            "--warmup", "0",
            "--output-dir", str(tmp),
        ]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = benchmark.main(argv)
        self.assertEqual(code, 0)
        data = json.loads(sorted(tmp.glob("benchmark_*.json"))[-1].read_text(encoding="utf-8"))
        sample = data["summaries"][0]["samples"][0]
        self.assertTrue(sample["ok"])
        self.assertIsNone(sample["completion_tokens"])
        self.assertIsNone(sample["tps"])
        self.assertGreater(sample["chars_per_sec"], 0)

    def test_rate_limit_taxonomy_and_fail_flag(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="bench-429-"))
        argv = [
            "--base-url", self.server.base_url,
            "--api-key", "test-key",
            "--models", "rate-limited-model",
            "--case", "zh_short_qa",
            "--repeat", "1",
            "--warmup", "0",
            "--fail-on-error",
            "--output-dir", str(tmp),
        ]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = benchmark.main(argv)
        self.assertEqual(code, 1)
        data = json.loads(sorted(tmp.glob("benchmark_*.json"))[-1].read_text(encoding="utf-8"))
        sample = data["summaries"][0]["samples"][0]
        self.assertFalse(sample["ok"])
        self.assertEqual(sample["error_class"], "rate_limit")
        self.assertEqual(sample["http_status"], 429)

    def test_non_stream(self) -> None:
        code, json_path = self._run("--no-stream", "--case", "zh_short_qa")
        self.assertEqual(code, 0)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        sample = data["summaries"][0]["samples"][0]
        self.assertFalse(sample["stream"])
        self.assertIsNone(sample["ttft"])
        self.assertEqual(sample["completion_tokens"], 100)
        self.assertAlmostEqual(sample["tps"], 100 / sample["latency"])
        self.assertTrue(sample["quality"])

    def test_rerank_case(self) -> None:
        code, json_path = self._run("--case", "rerank_docs", suite="full")
        self.assertEqual(code, 0)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        sample = data["summaries"][0]["samples"][0]
        self.assertTrue(sample["ok"])
        self.assertTrue(sample["quality"], sample["quality_detail"])
        self.assertEqual(sample["extra"]["top_index"], 0)
        self.assertGreater(sample["extra"]["top_score"], 0.9)

    def test_thinking_reasoning_tokens(self) -> None:
        code, json_path = self._run("--case", "math_thinking", suite="full")
        self.assertEqual(code, 0)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        sample = data["summaries"][0]["samples"][0]
        self.assertTrue(sample["ok"])
        self.assertTrue(sample["quality"], sample["quality_detail"])
        self.assertEqual(sample["reasoning_tokens"], 12)
        self.assertGreater(sample["reasoning_chars"], 0)
        self.assertIsNotNone(sample["ttft"])

    def test_merge_reports(self) -> None:
        _, first = self._run("--case", "zh_short_qa")
        _, second = self._run("--case", "zh_short_qa", model="second-model")
        tmp = Path(tempfile.mkdtemp(prefix="bench-merge-"))
        md_path = tmp / "merged.md"
        json_path = tmp / "merged.json"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = merge_reports.main([
                "--inputs", str(first), str(second),
                "--output-md", str(md_path),
                "--output-json", str(json_path),
            ])
        self.assertEqual(code, 0)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(data["meta"]["models"], ["mock-model", "second-model"])
        self.assertEqual(len(data["summaries"]), 2)
        self.assertIn("用例结果", md_path.read_text(encoding="utf-8"))

    def test_concurrency_probe(self) -> None:
        code, json_path = self._run(
            "--case", "zh_short_qa",
            "--concurrency", "2,4",
            "--concurrency-requests", "4",
        )
        self.assertEqual(code, 0)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual([p["level"] for p in data["concurrency"]], [2, 4])
        for probe in data["concurrency"]:
            self.assertEqual(probe["requests"], 4)
            self.assertEqual(probe["success_rate"], 1.0)
            self.assertGreater(probe["qps"], 0)
            self.assertEqual(probe["latency"]["n"], 4)


if __name__ == "__main__":
    unittest.main()
