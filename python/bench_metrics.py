#!/usr/bin/env python
# coding=utf-8
"""纯函数指标计算与质量校验，供 benchmark.py 与测试复用。

不依赖 openai/网络，保证指标数学可离线验证。
"""

from __future__ import annotations

import ast
import json
import math
import re
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

# ========== 分位数 ==========

def percentile(values: Sequence[float], q: float) -> float | None:
    """线性插值分位数（与 numpy.percentile 默认口径一致）。

    q=0/50/100 分别对应最小值/中位数/最大值；空序列返回 None。
    """
    if not 0 <= q <= 100:
        raise ValueError(f"q 必须位于 [0, 100]，实际为 {q}")
    data = sorted(float(v) for v in values)
    if not data:
        return None
    if len(data) == 1:
        return data[0]
    pos = (len(data) - 1) * (q / 100.0)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return data[lo]
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)


def summarize(values: Iterable[float | None]) -> dict[str, Any]:
    """汇总一组样本：均值、样本标准差、min/max、p50/p90/p99、均值 95% 置信区间半宽。

    空样本返回 n=0，其余字段为 None，调用方无需特判。
    """
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if n == 0:
        return {
            "n": 0,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "p50": None,
            "p90": None,
            "p99": None,
            "ci95": None,
        }
    mean = statistics.fmean(vals)
    std = statistics.stdev(vals) if n > 1 else 0.0
    ci95 = 1.96 * std / math.sqrt(n) if n > 1 else None
    return {
        "n": n,
        "mean": mean,
        "std": std,
        "min": min(vals),
        "max": max(vals),
        "p50": percentile(vals, 50),
        "p90": percentile(vals, 90),
        "p99": percentile(vals, 99),
        "ci95": ci95,
    }


# ========== 错误分类 ==========

ERROR_CLASSES = (
    "rate_limit",
    "auth",
    "bad_request",
    "server_error",
    "timeout",
    "connection",
    "parse_error",
    "unknown",
)


def classify_error(exc: BaseException) -> str:
    """把 SDK 异常映射为稳定的错误类别，便于跨语言对比与聚合。

    依据异常类名和 status_code 判断，不绑定 openai 具体版本。
    """
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)

    if status == 429 or "RateLimit" in name:
        return "rate_limit"
    if status in (401, 403) or "Authentication" in name or "PermissionDenied" in name:
        return "auth"
    if "Timeout" in name:
        return "timeout"
    if "Connection" in name:
        return "connection"
    if status is not None and 400 <= status < 500:
        return "bad_request"
    if status is not None and status >= 500:
        return "server_error"
    if isinstance(exc, json.JSONDecodeError) or "JSONDecode" in name:
        return "parse_error"
    return "unknown"


# ========== 响应质量校验 ==========

CHECK_TYPES = frozenset(
    {
        "contains_any",
        "contains_all",
        "not_contains",
        "regex",
        "json_valid",
        "json_keys",
        "min_chars",
        "python_valid",
    }
)

_FENCE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def _strip_fence(text: str) -> str:
    match = _FENCE_RE.search(text)
    return match.group(1) if match else text


def _norm(text: str, case_sensitive: bool) -> str:
    return text if case_sensitive else text.lower()


def _check_one(text: str, check: dict[str, Any]) -> tuple[bool, str]:
    kind = check.get("type")
    case_sensitive = bool(check.get("case_sensitive", False))
    haystack = _norm(text, case_sensitive)

    if kind == "contains_any":
        values = [str(v) for v in check["values"]]
        hit = [v for v in values if _norm(v, case_sensitive) in haystack]
        return (bool(hit), "ok" if hit else f"缺少任一关键词: {values}")

    if kind == "contains_all":
        values = [str(v) for v in check["values"]]
        missing = [v for v in values if _norm(v, case_sensitive) not in haystack]
        return (not missing, "ok" if not missing else f"缺少关键词: {missing}")

    if kind == "not_contains":
        values = [str(v) for v in check["values"]]
        hit = [v for v in values if _norm(v, case_sensitive) in haystack]
        return (not hit, "ok" if not hit else f"出现禁止内容: {hit}")

    if kind == "regex":
        pattern = re.compile(check["pattern"], 0 if case_sensitive else re.IGNORECASE)
        ok = bool(pattern.search(text))
        return (ok, "ok" if ok else f"正则未匹配: {check['pattern']}")

    if kind == "json_valid":
        try:
            json.loads(_strip_fence(text))
            return True, "ok"
        except json.JSONDecodeError as e:
            return False, f"JSON 解析失败: {e.msg}"

    if kind == "json_keys":
        try:
            obj = json.loads(_strip_fence(text))
        except json.JSONDecodeError as e:
            return False, f"JSON 解析失败: {e.msg}"
        if not isinstance(obj, dict):
            return False, "JSON 顶层不是对象"
        missing = [k for k in check["keys"] if k not in obj]
        return (not missing, "ok" if not missing else f"缺少字段: {missing}")

    if kind == "min_chars":
        n = len(text.strip())
        limit = int(check["value"])
        return (n >= limit, "ok" if n >= limit else f"长度 {n} < {limit}")

    if kind == "python_valid":
        code = _strip_fence(text)
        try:
            ast.parse(code)
        except SyntaxError as e:
            return False, f"Python 语法错误: {e.msg}"
        return True, "ok"

    raise ValueError(f"未知的 check 类型: {kind!r}")


def run_checks(text: str, checks: Sequence[dict[str, Any]] | None) -> tuple[bool | None, str]:
    """执行一组校验，返回 (全部通过?, 说明)。无校验时返回 (None, "no-check")。"""
    if not checks:
        return None, "no-check"
    failures = []
    for check in checks:
        ok, msg = _check_one(text, check)
        if not ok:
            failures.append(msg)
    return (not failures, "ok" if not failures else "; ".join(failures))


# ========== 单次请求样本 ==========

@dataclass
class Sample:
    """一次请求的原始指标，可序列化为 JSON。"""

    case_id: str
    dimension: str
    model: str
    ok: bool
    stream: bool
    latency: float
    ttft: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    chunks: int = 0
    gen_duration: float | None = None      # 首 token 到流结束的时长
    tps: float | None = None               # completion_tokens / gen_duration
    tpot: float | None = None              # gen_duration / (completion_tokens - 1)
    chars: int = 0
    reasoning_chars: int = 0
    chars_per_sec: float | None = None
    max_gap: float | None = None           # 流式相邻 chunk 最大间隔
    finish_reason: str | None = None
    quality: bool | None = None
    quality_detail: str = ""
    error: str | None = None
    error_class: str | None = None
    http_status: int | None = None
    embedding_dim: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CaseSummary:
    """同一模型、同一用例多次重复后的汇总。"""

    case_id: str
    dimension: str
    model: str
    samples: list[Sample] = field(default_factory=list)
    latency: dict[str, Any] = field(default_factory=dict)
    ttft: dict[str, Any] = field(default_factory=dict)
    tps: dict[str, Any] = field(default_factory=dict)
    tpot: dict[str, Any] = field(default_factory=dict)
    chars_per_sec: dict[str, Any] = field(default_factory=dict)
    reasoning_tokens: dict[str, Any] = field(default_factory=dict)
    success_rate: float = 0.0
    quality_rate: float | None = None
    errors: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "dimension": self.dimension,
            "model": self.model,
            "n": len(self.samples),
            "success_rate": self.success_rate,
            "quality_rate": self.quality_rate,
            "latency": self.latency,
            "ttft": self.ttft,
            "tps": self.tps,
            "tpot": self.tpot,
            "chars_per_sec": self.chars_per_sec,
            "reasoning_tokens": self.reasoning_tokens,
            "errors": self.errors,
            "samples": [s.to_dict() for s in self.samples],
        }


def summarize_samples(samples: Sequence[Sample]) -> CaseSummary:
    """把同一用例的多次采样聚合成 CaseSummary。"""
    if not samples:
        raise ValueError("samples 不能为空")
    first = samples[0]
    ok_samples = [s for s in samples if s.ok]
    scored = [s for s in ok_samples if s.quality is not None]

    errors: dict[str, int] = {}
    for s in samples:
        if not s.ok:
            key = s.error_class or "unknown"
            errors[key] = errors.get(key, 0) + 1

    return CaseSummary(
        case_id=first.case_id,
        dimension=first.dimension,
        model=first.model,
        samples=list(samples),
        latency=summarize(s.latency for s in ok_samples),
        ttft=summarize(s.ttft for s in ok_samples if s.ttft is not None),
        tps=summarize(s.tps for s in ok_samples if s.tps is not None),
        tpot=summarize(s.tpot for s in ok_samples if s.tpot is not None),
        chars_per_sec=summarize(s.chars_per_sec for s in ok_samples if s.chars_per_sec is not None),
        reasoning_tokens=summarize(
            s.reasoning_tokens for s in ok_samples if s.reasoning_tokens is not None
        ),
        success_rate=len(ok_samples) / len(samples),
        quality_rate=(sum(1 for s in scored if s.quality) / len(scored)) if scored else None,
        errors=errors,
    )


def aggregate_dimensions(summaries: Sequence[CaseSummary]) -> list[dict[str, Any]]:
    """按 (model, dimension) 合并样本，输出维度级指标。"""
    groups: dict[tuple[str, str], list[Sample]] = {}
    for summary in summaries:
        groups.setdefault((summary.model, summary.dimension), []).extend(summary.samples)

    rows = []
    for (model, dimension), samples in sorted(groups.items()):
        merged = summarize_samples(samples)
        rows.append({
            "model": model,
            "dimension": dimension,
            "n": len(samples),
            "success_rate": merged.success_rate,
            "quality_rate": merged.quality_rate,
            "latency": merged.latency,
            "ttft": merged.ttft,
            "tps": merged.tps,
            "tpot": merged.tpot,
            "reasoning_tokens": merged.reasoning_tokens,
            "errors": merged.errors,
        })
    return rows
