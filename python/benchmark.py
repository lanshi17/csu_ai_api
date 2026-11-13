#!/usr/bin/env python
# coding=utf-8
"""CSU AI API 基准测试：多维度用例 + 延迟/吞吐/质量指标。

与逐语言连通性测试互补：本脚本关注“指标与维度”，输出可直接引用的
JSON 原始数据与 Markdown 报告。

用法示例：
    uv run benchmark.py --list
    uv run benchmark.py --suite smoke --repeat 3 --concurrency 1,4,8
    uv run benchmark.py --suite full --models DeepSeek,GLM,Qwen
    uv run benchmark.py --case zh_short_qa --no-stream --repeat 5

说明：
- 不重试、不自动降级，失败按错误类别计数，避免污染延迟指标。
- `stream_options.include_usage` 不可用时自动回退，此时 token 指标为 None，
  吞吐仅提供 chars/s。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv
import httpx

import bench_metrics as bm

BENCH_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = BENCH_DIR / "datasets" / "benchmark_cases.json"
DEFAULT_OUTPUT = BENCH_DIR / "results"


# ========== 数据集 ==========

def load_dataset(path: Path) -> dict[str, Any]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    validate_dataset(dataset)
    return dataset


def validate_dataset(dataset: dict[str, Any]) -> None:
    dimensions = dataset.get("dimensions") or {}
    cases = dataset.get("cases") or []
    if not dimensions or not cases:
        raise ValueError("数据集必须包含 dimensions 与 cases")

    seen: set[str] = set()
    problems: list[str] = []
    for case in cases:
        cid = case.get("id")
        if not cid:
            problems.append("存在缺少 id 的用例")
            continue
        if cid in seen:
            problems.append(f"用例 id 重复: {cid}")
        seen.add(cid)

        if case.get("dimension") not in dimensions:
            problems.append(f"{cid}: 未知维度 {case.get('dimension')!r}")

        if case.get("type") == "embedding":
            if not case.get("model") or not case.get("input"):
                problems.append(f"{cid}: embedding 用例需要 model 与 input")
        elif case.get("type") == "rerank":
            for field in ("model", "query", "documents"):
                if not case.get(field):
                    problems.append(f"{cid}: rerank 用例需要 {field}")
        else:
            if not case.get("messages") and not case.get("build"):
                problems.append(f"{cid}: 缺少 messages/build")
            build = case.get("build")
            if build:
                if build.get("type") != "needle":
                    problems.append(f"{cid}: 未知 build 类型 {build.get('type')!r}")
                elif not build.get("needle") or not build.get("question"):
                    problems.append(f"{cid}: needle build 需要 needle 与 question")

        for check in case.get("checks") or []:
            if check.get("type") not in bm.CHECK_TYPES:
                problems.append(f"{cid}: 未知 check 类型 {check.get('type')!r}")

    if problems:
        raise ValueError("数据集校验失败:\n  " + "\n  ".join(problems))


def select_cases(
    dataset: dict[str, Any],
    suite: str,
    case_ids: Sequence[str] | None,
    dimensions: Sequence[str] | None,
    tags: Sequence[str] | None,
) -> list[dict[str, Any]]:
    cases = [c for c in dataset["cases"] if suite in (c.get("suites") or ["full"])]
    if case_ids:
        wanted = set(case_ids)
        cases = [c for c in cases if c["id"] in wanted]
        missing = wanted - {c["id"] for c in cases}
        if missing:
            raise SystemExit(f"未找到用例: {', '.join(sorted(missing))}")
    if dimensions:
        wanted_dims = set(dimensions)
        cases = [c for c in cases if c["dimension"] in wanted_dims]
    if tags:
        wanted_tags = set(tags)
        cases = [c for c in cases if wanted_tags & set(c.get("tags") or [])]
    if not cases:
        raise SystemExit("筛选后没有用例可运行")
    return cases


def build_messages(case: dict[str, Any]) -> list[dict[str, str]]:
    build = case.get("build")
    if not build:
        return list(case["messages"])
    if build["type"] == "needle":
        filler = "\n".join(
            f"第 {i} 段：这是用于长上下文测试的填充内容，与问题无关，请忽略。"
            for i in range(1, int(build["filler_sentences"]) + 1)
        )
        content = (
            f"{filler}\n\n"
            f"重要信息：本次测试的暗号是 {build['needle']}，请牢记。\n\n"
            f"问题：{build['question']}"
        )
        return [{"role": "user", "content": content}]
    raise ValueError(f"未知的 build 类型: {build['type']!r}")


# ========== 单次请求 ==========

@dataclass(frozen=True)
class RunConfig:
    stream: bool
    timeout: float
    reasoning_effort: str | None = None


def _usage_tuple(usage: Any) -> tuple[int | None, int | None, int | None]:
    if usage is None:
        return None, None, None
    return (
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
        getattr(usage, "total_tokens", None),
    )


def _reasoning_tokens(usage: Any) -> int | None:
    details = getattr(usage, "completion_tokens_details", None)
    if details is None:
        return None
    return getattr(details, "reasoning_tokens", None)


class RateGate:
    """按最小间隔均匀放行请求，避免触发网关 429。"""

    def __init__(self, interval: float) -> None:
        self.interval = max(0.0, interval)
        self.lock = threading.Lock()
        self.next_slot = 0.0

    def wait(self) -> None:
        if self.interval <= 0:
            return
        with self.lock:
            now = time.perf_counter()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        delay = slot - time.perf_counter()
        if delay > 0:
            time.sleep(delay)


# 输出过短时解码速率被计时噪声放大，低于阈值不输出 tok/s 与 TPOT
MIN_RATE_TOKENS = 20


def _rate_metrics(
    completion_tokens: int | None, window: float | None
) -> tuple[float | None, float | None]:
    if (
        completion_tokens is None
        or completion_tokens < MIN_RATE_TOKENS
        or window is None
        or window <= 0
    ):
        return None, None
    tps = completion_tokens / window
    tpot = window / (completion_tokens - 1) if completion_tokens > 1 else None
    return tps, tpot


def _chat_kwargs(
    model: str,
    messages: list[dict[str, str]],
    case: dict[str, Any],
    cfg: RunConfig,
    stream: bool,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": int(case.get("max_tokens", 512)),
        "temperature": float(case.get("temperature", 0.2)),
        "stream": stream,
        "timeout": cfg.timeout,
    }
    if case.get("response_format"):
        kwargs["response_format"] = case["response_format"]
    effort = case.get("reasoning_effort", cfg.reasoning_effort)
    if effort and effort != "default":
        kwargs["reasoning_effort"] = effort
    return kwargs


def _open_stream(client: Any, kwargs: dict[str, Any]) -> Any:
    """请求 usage 的流式调用；服务端不支持 stream_options 时回退一次。"""
    try:
        return client.chat.completions.create(
            **kwargs, stream_options={"include_usage": True}
        )
    except Exception as exc:  # noqa: BLE001 - 需要按状态码判断是否回退
        status = getattr(exc, "status_code", None)
        if status in (400, 422):
            return client.chat.completions.create(**kwargs)
        raise


def _score(content: str, case: dict[str, Any]) -> tuple[bool | None, str]:
    return bm.run_checks(content, case.get("checks"))


def run_embedding(client: Any, case: dict[str, Any], cfg: RunConfig) -> bm.Sample:
    model = case["model"]
    start = time.perf_counter()
    try:
        resp = client.embeddings.create(
            model=model, input=case["input"], timeout=cfg.timeout
        )
        latency = time.perf_counter() - start
        vectors = [item.embedding for item in resp.data]
        dims = {len(v) for v in vectors}
        valid = bool(vectors) and len(dims) == 1 and next(iter(dims)) > 0
        detail = "ok" if valid else f"非法向量: n={len(vectors)}, dims={sorted(dims)}"
        prompt_tokens, _, total_tokens = _usage_tuple(getattr(resp, "usage", None))
        return bm.Sample(
            case_id=case["id"],
            dimension=case["dimension"],
            model=model,
            ok=True,
            stream=False,
            latency=latency,
            prompt_tokens=prompt_tokens,
            total_tokens=total_tokens,
            quality=valid,
            quality_detail=detail,
            embedding_dim=next(iter(dims)) if len(dims) == 1 else None,
        )
    except Exception as exc:  # noqa: BLE001 - 记录原始错误
        return bm.Sample(
            case_id=case["id"],
            dimension=case["dimension"],
            model=model,
            ok=False,
            stream=False,
            latency=time.perf_counter() - start,
            error=f"{type(exc).__name__}: {exc}",
            error_class=bm.classify_error(exc),
            http_status=getattr(exc, "status_code", None),
        )


def run_chat(
    client: Any, case: dict[str, Any], model: str, cfg: RunConfig
) -> bm.Sample:
    messages = build_messages(case)
    start = time.perf_counter()

    try:
        if not cfg.stream:
            resp = client.chat.completions.create(
                **_chat_kwargs(model, messages, case, cfg, stream=False)
            )
            latency = time.perf_counter() - start
            choice = resp.choices[0]
            message = choice.message
            content = getattr(message, "content", None) or ""
            reasoning = (
                getattr(message, "reasoning", None)
                or getattr(message, "reasoning_content", None)
                or ""
            )
            prompt_tokens, completion_tokens, total_tokens = _usage_tuple(
                getattr(resp, "usage", None)
            )
            reason_tokens = _reasoning_tokens(getattr(resp, "usage", None))
            chars = len(content)
            quality, detail = _score(content, case)
            return bm.Sample(
                case_id=case["id"],
                dimension=case["dimension"],
                model=model,
                ok=True,
                stream=False,
                latency=latency,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                reasoning_tokens=reason_tokens,
                chunks=1,
                gen_duration=latency,
                tps=(completion_tokens / latency) if completion_tokens else None,
                tpot=(latency / completion_tokens) if completion_tokens else None,
                chars=chars,
                reasoning_chars=len(reasoning),
                chars_per_sec=(chars / latency) if latency > 0 else None,
                finish_reason=getattr(choice, "finish_reason", None),
                quality=quality,
                quality_detail=detail,
            )

        stream = _open_stream(client, _chat_kwargs(model, messages, case, cfg, stream=True))
        first_at: float | None = None
        last_content_at: float | None = None
        content_times: list[float] = []
        text_parts: list[str] = []
        reasoning_chars = 0
        usage = None
        finish_reason = None

        for chunk in stream:
            now = time.perf_counter()
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = chunk_usage

            for choice in getattr(chunk, "choices", None) or []:
                if getattr(choice, "finish_reason", None):
                    finish_reason = choice.finish_reason
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                reasoning = (
                    getattr(delta, "reasoning", None)
                    or getattr(delta, "reasoning_content", None)
                    or ""
                )
                content = getattr(delta, "content", None) or ""
                if reasoning:
                    reasoning_chars += len(reasoning)
                    if first_at is None:
                        first_at = now
                if content:
                    if first_at is None:
                        first_at = now
                    last_content_at = now
                    content_times.append(now)
                    text_parts.append(content)

        end = time.perf_counter()
        latency = end - start
        content = "".join(text_parts)
        ttft = (first_at - start) if first_at is not None else None
        prompt_tokens, completion_tokens, total_tokens = _usage_tuple(usage)
        reason_tokens = _reasoning_tokens(usage)
        gen_duration = (end - first_at) if first_at is not None else latency
        chars = len(content)
        gaps = [b - a for a, b in zip(content_times, content_times[1:])]
        quality, detail = _score(content, case)
        tps, tpot = _rate_metrics(completion_tokens, gen_duration)

        return bm.Sample(
            case_id=case["id"],
            dimension=case["dimension"],
            model=model,
            ok=True,
            stream=True,
            latency=latency,
            ttft=ttft,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            reasoning_tokens=reason_tokens,
            chunks=len(content_times),
            gen_duration=gen_duration,
            tps=tps,
            tpot=tpot,
            chars=chars,
            reasoning_chars=reasoning_chars,
            chars_per_sec=(chars / gen_duration) if gen_duration > 0 else None,
            max_gap=max(gaps) if gaps else None,
            finish_reason=finish_reason,
            quality=quality,
            quality_detail=detail,
        )

    except Exception as exc:  # noqa: BLE001 - 记录原始错误
        return bm.Sample(
            case_id=case["id"],
            dimension=case["dimension"],
            model=model,
            ok=False,
            stream=cfg.stream,
            latency=time.perf_counter() - start,
            error=f"{type(exc).__name__}: {exc}",
            error_class=bm.classify_error(exc),
            http_status=getattr(exc, "status_code", None),
        )


def run_rerank(client: Any, case: dict[str, Any], cfg: RunConfig) -> bm.Sample:
    """Jina/Cohere 风格 /rerank 探针，校验排序与首位命中。"""
    url = f"{str(client.base_url).rstrip('/')}/rerank"
    payload = {
        "model": case["model"],
        "query": case["query"],
        "documents": case["documents"],
    }
    if case.get("top_n"):
        payload["top_n"] = int(case["top_n"])

    start = time.perf_counter()
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {client.api_key}"},
            json=payload,
            timeout=cfg.timeout,
        )
        latency = time.perf_counter() - start
        resp.raise_for_status()
        results = resp.json().get("results") or []
        scores = [float(item.get("relevance_score", 0.0)) for item in results]
        top_index = results[0].get("index") if results else None
        top_score = scores[0] if scores else None
        expected = int(case.get("top_index", 0))
        monotonic = all(a >= b for a, b in zip(scores, scores[1:]))
        valid = bool(results) and monotonic and top_index == expected
        if not results:
            detail = "返回结果为空"
        elif not monotonic:
            detail = f"分数未降序: {scores}"
        elif top_index != expected:
            detail = f"首位 index={top_index}，期望 {expected}"
        else:
            detail = "ok"
        return bm.Sample(
            case_id=case["id"],
            dimension=case["dimension"],
            model=case["model"],
            ok=True,
            stream=False,
            latency=latency,
            quality=valid,
            quality_detail=detail,
            extra={
                "top_index": top_index,
                "top_score": top_score,
                "scores": scores,
                "documents": len(results),
            },
        )
    except Exception as exc:  # noqa: BLE001 - 记录原始错误
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
        return bm.Sample(
            case_id=case["id"],
            dimension=case["dimension"],
            model=case["model"],
            ok=False,
            stream=False,
            latency=time.perf_counter() - start,
            error=f"{type(exc).__name__}: {exc}",
            error_class=bm.classify_error(exc),
            http_status=status,
        )


def run_case(client: Any, case: dict[str, Any], model: str, cfg: RunConfig) -> bm.Sample:
    if case.get("type") == "embedding":
        return run_embedding(client, case, cfg)
    if case.get("type") == "rerank":
        return run_rerank(client, case, cfg)
    return run_chat(client, case, model, cfg)


# ========== 并发探测 ==========

def run_concurrency(
    client: Any,
    case: dict[str, Any],
    model: str,
    cfg: RunConfig,
    level: int,
    total: int,
    gate: RateGate | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    samples: list[bm.Sample] = []
    with ThreadPoolExecutor(max_workers=level) as pool:
        futures = []
        for _ in range(total):
            if gate is not None:
                gate.wait()
            futures.append(pool.submit(run_case, client, case, model, cfg))
        for future in as_completed(futures):
            samples.append(future.result())
    wall = time.perf_counter() - started

    ok = [s for s in samples if s.ok]
    tokens = sum(s.completion_tokens or 0 for s in ok)
    chars = sum(s.chars for s in ok)
    errors = Counter(s.error_class or "unknown" for s in samples if not s.ok)
    return {
        "model": model,
        "case_id": case["id"],
        "level": level,
        "requests": len(samples),
        "success_rate": len(ok) / len(samples) if samples else 0.0,
        "wall": wall,
        "qps": (len(samples) / wall) if wall > 0 else None,
        "output_tps": (tokens / wall) if tokens and wall > 0 else None,
        "chars_per_sec": (chars / wall) if chars and wall > 0 else None,
        "latency": bm.summarize(s.latency for s in ok),
        "ttft": bm.summarize(s.ttft for s in ok if s.ttft is not None),
        "errors": dict(errors),
    }


# ========== 报告 ==========

def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _pct(value: Any) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _width(text: str) -> int:
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def render_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    cells = [[str(c) for c in row] for row in rows]
    widths = [_width(h) for h in headers]
    for row in cells:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _width(cell))
    lines = ["  ".join(_pad(h, widths[i]) for i, h in enumerate(headers))]
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in cells:
        lines.append("  ".join(_pad(cell, widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


def _case_rows(summaries: Sequence[dict[str, Any]], multi_model: bool) -> list[list[str]]:
    rows = []
    for s in summaries:
        row = []
        if multi_model:
            row.append(s["model"])
        row.extend(
            [
                s["dimension"],
                s["case_id"],
                str(s["n"]),
                _pct(s["success_rate"]),
                _pct(s["quality_rate"]),
                _fmt(s["ttft"].get("p50")),
                _fmt(s["ttft"].get("p99")),
                _fmt(s["latency"].get("p50")),
                _fmt(s["latency"].get("p90")),
                _fmt(s["latency"].get("p99")),
                _fmt(s["tps"].get("mean"), 1),
                _fmt(s["reasoning_tokens"].get("mean"), 1),
                _fmt(s["tpot"].get("mean") * 1000 if s["tpot"].get("mean") is not None else None, 1),
            ]
        )
        rows.append(row)
    return rows


def _case_headers(multi_model: bool) -> list[str]:
    headers = ["维度", "用例", "n", "成功", "质量", "TTFT p50", "TTFT p99",
               "延迟 p50", "延迟 p90", "延迟 p99", "tok/s", "推理 tok", "TPOT ms"]
    return (["模型"] + headers) if multi_model else headers


def _dimension_rows(dims: Sequence[dict[str, Any]], multi_model: bool) -> list[list[str]]:
    rows = []
    for d in dims:
        row = []
        if multi_model:
            row.append(d["model"])
        row.extend(
            [
                d["dimension"],
                str(d["n"]),
                _pct(d["success_rate"]),
                _pct(d["quality_rate"]),
                _fmt(d["ttft"].get("p50")),
                _fmt(d["latency"].get("p50")),
                _fmt(d["latency"].get("p99")),
                _fmt(d["tps"].get("mean"), 1),
                _fmt(d["reasoning_tokens"].get("mean"), 1),
                _fmt(d["tpot"].get("mean") * 1000 if d["tpot"].get("mean") is not None else None, 1),
                ", ".join(f"{k}:{v}" for k, v in sorted(d["errors"].items())) or "-",
            ]
        )
        rows.append(row)
    return rows


def _dimension_headers(multi_model: bool) -> list[str]:
    headers = ["维度", "n", "成功", "质量", "TTFT p50", "延迟 p50", "延迟 p99",
               "tok/s", "推理 tok", "TPOT ms", "错误"]
    return (["模型"] + headers) if multi_model else headers


def _concurrency_rows(probes: Sequence[dict[str, Any]], multi_model: bool) -> list[list[str]]:
    rows = []
    for p in probes:
        row = []
        if multi_model:
            row.append(p["model"])
        row.extend(
            [
                str(p["level"]),
                str(p["requests"]),
                _pct(p["success_rate"]),
                _fmt(p["wall"], 2),
                _fmt(p["qps"], 2),
                _fmt(p["output_tps"], 1),
                _fmt(p["latency"].get("p50")),
                _fmt(p["latency"].get("p99")),
                _fmt(p["ttft"].get("p50")),
                ", ".join(f"{k}:{v}" for k, v in sorted(p["errors"].items())) or "-",
            ]
        )
        rows.append(row)
    return rows


def _concurrency_headers(multi_model: bool) -> list[str]:
    headers = ["并发", "请求", "成功", "墙钟 s", "QPS", "输出 tok/s",
               "延迟 p50", "延迟 p99", "TTFT p50", "错误"]
    return (["模型"] + headers) if multi_model else headers


def write_json(data: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(data: dict[str, Any], path: Path) -> None:
    meta = data["meta"]
    multi_model = len(meta["models"]) > 1
    lines = [
        "# CSU AI API 基准报告",
        "",
        f"- 时间：{meta['timestamp']}",
        f"- 端点：`{meta['base_url']}`",
        f"- 模型：{', '.join(f'`{m}`' for m in meta['models'])}",
        f"- 用例集：{meta['suite']}（数据集 v{meta['dataset_version']}，{meta['case_count']} 个用例，重复 {meta['repeat']} 次）",
        f"- 模式：{'流式' if meta['stream'] else '非流式'}；超时 {meta['timeout']}s；"
        f"reasoning={meta.get('reasoning_effort', '-')}；间隔 {meta.get('min_interval', 0)}s",
        "",
        "## 用例结果",
        "",
        "| " + " | ".join(_case_headers(multi_model)) + " |",
        "|" + "|".join(["---"] * len(_case_headers(multi_model))) + "|",
    ]
    for row in _case_rows(data["summaries"], multi_model):
        lines.append("| " + " | ".join(row) + " |")

    lines += [
        "",
        "## 维度汇总",
        "",
        "| " + " | ".join(_dimension_headers(multi_model)) + " |",
        "|" + "|".join(["---"] * len(_dimension_headers(multi_model))) + "|",
    ]
    for row in _dimension_rows(data["dimensions"], multi_model):
        lines.append("| " + " | ".join(row) + " |")

    if data["concurrency"]:
        lines += [
            "",
            "## 并发扩展",
            "",
            "| " + " | ".join(_concurrency_headers(multi_model)) + " |",
            "|" + "|".join(["---"] * len(_concurrency_headers(multi_model))) + "|",
        ]
        for row in _concurrency_rows(data["concurrency"], multi_model):
            lines.append("| " + " | ".join(row) + " |")

    error_rows = []
    for summary in data["summaries"]:
        for sample in summary["samples"]:
            if not sample["ok"]:
                error_rows.append([
                    sample["model"],
                    sample["case_id"],
                    sample["error_class"] or "unknown",
                    _fmt(sample["http_status"]),
                    (sample["error"] or "")[:120],
                ])
    if error_rows:
        headers = ["模型", "用例", "类别", "HTTP", "错误"]
        lines += [
            "",
            "## 错误明细",
            "",
            "| " + " | ".join(headers) + " |",
            "|" + "|".join(["---"] * len(headers)) + "|",
        ]
        for row in error_rows:
            lines.append("| " + " | ".join(row) + " |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_report(data: dict[str, Any]) -> None:
    multi_model = len(data["meta"]["models"]) > 1
    print("\n" + "=" * 100)
    print("用例结果")
    print("=" * 100)
    print(render_table(_case_headers(multi_model), _case_rows(data["summaries"], multi_model)))
    print("\n" + "=" * 100)
    print("维度汇总")
    print("=" * 100)
    print(render_table(_dimension_headers(multi_model), _dimension_rows(data["dimensions"], multi_model)))
    if data["concurrency"]:
        print("\n" + "=" * 100)
        print("并发扩展")
        print("=" * 100)
        print(render_table(
            _concurrency_headers(multi_model),
            _concurrency_rows(data["concurrency"], multi_model),
        ))


# ========== CLI ==========

def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CSU AI API 多维度基准测试",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--base-url", default=None, help="API base URL")
    parser.add_argument("--api-key", default=None, help="API key（默认读 .env/API_KEY）")
    parser.add_argument("--models", default=None, help="逗号分隔的模型列表")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="用例集 JSON 路径")
    parser.add_argument("--suite", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--case", action="append", help="只运行指定用例 id，可重复")
    parser.add_argument("--dimension", action="append", help="只运行指定维度，可重复")
    parser.add_argument("--tag", action="append", help="只运行指定 tag，可重复")
    parser.add_argument("--repeat", type=int, default=3, help="每个用例重复次数（≥1）")
    parser.add_argument("--warmup", type=int, default=1, help="每个模型预热请求数")
    parser.add_argument("--stream", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--reasoning",
        choices=["none", "minimal", "low", "medium", "high", "default"],
        default=os.getenv("REASONING_EFFORT", "none"),
        help="chat 推理强度；default 表示不传该参数",
    )
    parser.add_argument("--min-interval", type=float, default=0.0,
                        help="请求最小间隔秒数（如 6.5 约等于 9 次/分钟）")
    parser.add_argument("--concurrency", default="", help="并发档位，如 1,4,8；留空不测")
    parser.add_argument("--concurrency-requests", type=int, default=0,
                        help="每档位的请求数（默认 并发数 × 4）")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--list", action="store_true", help="列出用例后退出")
    parser.add_argument("--fail-on-error", action="store_true", help="任一请求失败则退出码 1")
    parser.add_argument("--quiet", action="store_true", help="不打印进度")
    return parser.parse_args(argv)


def _print_catalog(dataset: dict[str, Any]) -> None:
    print(f"数据集 v{dataset['version']}（更新于 {dataset['updated']}）")
    print("\n维度:")
    for key, dim in dataset["dimensions"].items():
        count = sum(1 for c in dataset["cases"] if c["dimension"] == key)
        print(f"  {key:<14} {dim['name']:<8} {count} 个用例  {dim['description']}")
    print("\n用例:")
    for case in dataset["cases"]:
        suites = ",".join(case.get("suites") or [])
        print(f"  {case['id']:<22} {case['dimension']:<14} [{suites}]  {case.get('tags', [])}")


def _parse_levels(raw: str) -> list[int]:
    levels = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            level = int(part)
        except ValueError as exc:
            raise SystemExit(f"非法并发档位: {part!r}") from exc
        if level < 1:
            raise SystemExit("并发档位必须 ≥ 1")
        levels.append(level)
    return levels


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv(BENCH_DIR / ".env")
    load_dotenv(BENCH_DIR.parent / ".env")  # 根目录统一配置（本地优先）
    args = parse_args(argv)

    dataset = load_dataset(Path(args.dataset))
    if args.list:
        _print_catalog(dataset)
        return 0

    base_url = args.base_url or os.getenv("API_BASE_URL", "https://api.chat.csu.edu.cn/v1")
    api_key = args.api_key or os.getenv("API_KEY", "")
    if not api_key:
        print("错误: 未提供 API Key（--api-key 或 .env 中的 API_KEY）", file=sys.stderr)
        return 2
    if args.repeat < 1:
        print("错误: --repeat 必须 ≥ 1", file=sys.stderr)
        return 2
    levels = _parse_levels(args.concurrency)

    env_model = os.getenv("MODEL_NAME", "DeepSeek")
    models = [m.strip() for m in (args.models or env_model).split(",") if m.strip()]
    cases = select_cases(dataset, args.suite, args.case, args.dimension, args.tag)
    cfg = RunConfig(
        stream=bool(args.stream),
        timeout=float(args.timeout),
        reasoning_effort=None if args.reasoning == "default" else args.reasoning,
    )
    gate = RateGate(args.min_interval)

    try:
        from openai import OpenAI
        import openai
    except ImportError as exc:  # pragma: no cover - 环境缺失时给出明确提示
        print(f"错误: 需要安装 openai SDK: {exc}", file=sys.stderr)
        return 2

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=cfg.timeout,
        max_retries=0,
    )

    print(f"端点: {base_url}")
    print(f"模型: {', '.join(models)}")
    print(f"用例: {len(cases)} 个，重复 {args.repeat} 次，模式: {'流式' if cfg.stream else '非流式'}")
    print(f"用例集: {args.suite}（数据集 v{dataset['version']}）")

    summaries: list[bm.CaseSummary] = []
    executed: set[tuple[str, str]] = set()
    total = len(models) * len(cases) * args.repeat
    index = 0

    for model in models:
        for _ in range(max(0, args.warmup)):
            warmup_case = next(
                (c for c in cases if c.get("type") not in ("embedding", "rerank")), None
            )
            if warmup_case is None:
                break
            gate.wait()
            sample = run_case(client, warmup_case, model, cfg)
            if not args.quiet:
                status = "ok" if sample.ok else f"失败({sample.error_class})"
                print(f"[预热] {model} / {warmup_case['id']}: {status}")
            if sample.error_class == "auth":
                print("错误: 鉴权失败（401/403），请检查 API_KEY", file=sys.stderr)
                return 2

        for case in cases:
            effective_model = case.get("model") or model
            key = (case["id"], effective_model)
            if key in executed:
                continue
            executed.add(key)
            samples = []
            for _ in range(args.repeat):
                gate.wait()
                samples.append(run_case(client, case, effective_model, cfg))
            summary = bm.summarize_samples(samples)
            summaries.append(summary)
            index += args.repeat

            if not args.quiet:
                last = samples[-1]
                detail = (
                    f"{last.latency:.3f}s"
                    if last.ok
                    else f"{last.error_class}: {last.error}"
                )
                print(
                    f"[{index}/{total}] {effective_model} / {case['id']}: "
                    f"{'ok' if last.ok else 'fail'} {detail}"
                )

    dimensions = bm.aggregate_dimensions(summaries)

    probes: list[dict[str, Any]] = []
    if levels:
        probe_case = next((c for c in cases if c["id"] == "zh_short_qa"), None)
        if probe_case is None:
            probe_case = next(
                (c for c in cases if c.get("type") not in ("embedding", "rerank")), None
            )
        if probe_case is not None:
            for model in models:
                for level in levels:
                    total_requests = args.concurrency_requests or level * 4
                    probe = run_concurrency(
                        client, probe_case, model, cfg, level, total_requests, gate
                    )
                    probes.append(probe)
                    if not args.quiet:
                        print(
                            f"[并发 {level}] {model}: 成功 {_pct(probe['success_rate'])}, "
                            f"QPS {_fmt(probe['qps'], 2)}, p99 {_fmt(probe['latency'].get('p99'))}s"
                        )

    timestamp = datetime.now().astimezone()
    data = {
        "meta": {
            "timestamp": timestamp.isoformat(timespec="seconds"),
            "base_url": base_url,
            "models": models,
            "suite": args.suite,
            "case_count": len(cases),
            "repeat": args.repeat,
            "stream": cfg.stream,
            "timeout": cfg.timeout,
            "reasoning_effort": args.reasoning,
            "min_interval": args.min_interval,
            "dataset_version": dataset["version"],
            "python": sys.version.split()[0],
            "openai_sdk": getattr(openai, "__version__", "unknown"),
            "platform": f"{platform.system()} {platform.machine()}",
        },
        "dimensions_meta": dataset["dimensions"],
        "summaries": [s.to_dict() for s in summaries],
        "dimensions": dimensions,
        "concurrency": probes,
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp.strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"benchmark_{stamp}.json"
    md_path = output_dir / f"benchmark_{stamp}.md"
    write_json(data, json_path)
    write_markdown(data, md_path)

    print_report(data)
    print(f"\nJSON: {json_path}")
    print(f"Markdown: {md_path}")

    if args.fail_on_error:
        failed = sum(1 for s in summaries for sample in s.samples if not sample.ok)
        if failed:
            print(f"\n{failed} 个请求失败（--fail-on-error）", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
