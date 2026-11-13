#!/usr/bin/env python
# coding=utf-8
"""速率限制与稳定性压测。

扩展指标：成功率、QPS、延迟分位数（p50/p90/p99）、错误类别分布、
固定 QPS 下的积压（backlog）以及阶梯式限流探测结果。

用法：
    uv run rate_limit_test.py --mode find_limit
    uv run rate_limit_test.py --mode fixed_qps --rps 5 --duration 60
    uv run rate_limit_test.py --mode single_test --requests 20 --workers 20
    uv run rate_limit_test.py --mode single_test --json-out results/rate_limit.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI

from bench_metrics import classify_error, summarize

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")  # 根目录统一配置（本地优先）

# 兼容旧变量名 MY_API_KEY / MY_API_BASE / MY_MODEL
API_KEY = os.getenv("API_KEY") or os.getenv("MY_API_KEY", "")
API_BASE_URL = (
    os.getenv("API_BASE_URL")
    or os.getenv("MY_API_BASE")
    or "https://api.chat.csu.edu.cn/v1"
)
MODEL_NAME = os.getenv("MODEL_NAME") or os.getenv("MY_MODEL", "DeepSeek")


# ========== 统计 ==========

class TestStats:
    """线程安全的请求结果收集器。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.total_requests = 0
        self.success_count = 0
        self.rate_limited_count = 0
        self.failed_count = 0
        self.latencies: list[float] = []
        self.success_latencies: list[float] = []
        self.error_classes: Counter[str] = Counter()
        self.http_statuses: Counter[int] = Counter()
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.max_backlog = 0
        self._inflight = 0

    def request_started(self) -> None:
        with self.lock:
            self._inflight += 1
            self.max_backlog = max(self.max_backlog, self._inflight)

    def request_finished(self) -> None:
        with self.lock:
            self._inflight -= 1

    def record(self, result: dict) -> None:
        with self.lock:
            self.total_requests += 1
            self.latencies.append(result["latency"])
            if result["status"] == "success":
                self.success_count += 1
                self.success_latencies.append(result["latency"])
            elif result["status"] == "rate_limited":
                self.rate_limited_count += 1
                self.failed_count += 1
                self.error_classes["rate_limit"] += 1
            else:
                self.failed_count += 1
                self.error_classes[result.get("error_class") or "unknown"] += 1
                if result.get("http_status"):
                    self.http_statuses[int(result["http_status"])] += 1

    def summary(self, target_rps: float | None = None) -> dict:
        with self.lock:
            total = self.total_requests
            wall = (self.end_time - self.start_time) if self.start_time and self.end_time else 0.0
            success_rate = self.success_count / total if total else 0.0
            return {
                "requests": total,
                "success": self.success_count,
                "failed": self.failed_count,
                "rate_limited": self.rate_limited_count,
                "success_rate": success_rate,
                "wall": wall,
                "qps": (total / wall) if wall > 0 else None,
                "target_rps": target_rps,
                "max_backlog": self.max_backlog,
                "latency": summarize(self.latencies),
                "latency_success": summarize(self.success_latencies),
                "errors": dict(self.error_classes),
                "http_statuses": {str(k): v for k, v in sorted(self.http_statuses.items())},
            }


stats = TestStats()
stats_lock = threading.Lock()


def _reset_stats() -> TestStats:
    global stats
    with stats_lock:
        stats = TestStats()
    return stats


# ========== 单次请求 ==========

def make_request(client: OpenAI, model: str, request_id: int, timeout: float) -> dict:
    stats.request_started()
    start = time.perf_counter()
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"压测请求 #{request_id}，请只回复 ok"}],
            max_tokens=16,
            temperature=0.1,
            stream=False,
            timeout=timeout,
        )
        result = {"id": request_id, "status": "success", "latency": time.perf_counter() - start}
    except Exception as exc:  # noqa: BLE001 - 按 SDK 异常类别统计
        latency = time.perf_counter() - start
        error_class = classify_error(exc)
        status = getattr(exc, "status_code", None)
        result = {
            "id": request_id,
            "status": "rate_limited" if error_class == "rate_limit" else "error",
            "latency": latency,
            "error_class": error_class,
            "http_status": status,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        stats.request_finished()

    stats.record(result)
    return result


# ========== 场景 ==========

def run_concurrent_burst(client: OpenAI, model: str, requests: int, workers: int, timeout: float) -> dict:
    local = _reset_stats()
    logger.info(f"突发并发: {requests} 请求 / {workers} 线程")
    local.start_time = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(make_request, client, model, i, timeout) for i in range(requests)
        ]
        for future in as_completed(futures):
            future.result()
    local.end_time = time.perf_counter()
    return local.summary()


def validate_config() -> bool:
    if not API_KEY:
        logger.error("请设置 API_KEY（或旧变量 MY_API_KEY），可写入 python/.env")
        return False
    return True


def find_limit(
    client: OpenAI,
    model: str,
    ladder: list[int],
    cooldown: float,
    threshold: float,
    timeout: float,
) -> dict:
    logger.info(f"阶梯探测: {ladder}，成功率阈值 {threshold:.0%}，间隔 {cooldown:.0f}s")
    results = []
    limit_level = 0

    for index, level in enumerate(ladder):
        logger.info(f"\n--- 并发 {level} ---")
        summary = run_concurrent_burst(client, model, level, level, timeout)
        summary["level"] = level
        results.append(summary)

        logger.info(
            f"成功 {summary['success']}/{summary['requests']} "
            f"({summary['success_rate']:.1%}), 限流 {summary['rate_limited']}, "
            f"p50 {summary['latency']['p50']:.3f}s, p99 {summary['latency']['p99']:.3f}s"
        )

        if summary["success_rate"] >= threshold:
            limit_level = level
        else:
            logger.warning(f"并发 {level} 成功率低于阈值，停止探测")
            break

        if index < len(ladder) - 1:
            logger.info(f"冷却 {cooldown:.0f}s 后继续...")
            time.sleep(cooldown)

    return {
        "mode": "find_limit",
        "threshold": threshold,
        "ladder": ladder,
        "limit_level": limit_level,
        "results": results,
    }


def fixed_rps(
    client: OpenAI,
    model: str,
    rps: float,
    duration: float,
    workers: int,
    timeout: float,
) -> dict:
    local = _reset_stats()
    interval = 1.0 / rps
    workers = workers or max(4, min(128, math.ceil(rps * 2)))
    logger.info(f"固定 QPS: {rps}/s，持续 {duration:.0f}s，线程 {workers}")

    local.start_time = time.perf_counter()
    deadline = local.start_time + duration
    next_slot = local.start_time
    request_id = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = []
        while True:
            now = time.perf_counter()
            if now >= deadline:
                break
            if next_slot > now:
                time.sleep(next_slot - now)
            pending.append(executor.submit(make_request, client, model, request_id, timeout))
            request_id += 1
            next_slot += interval

            if request_id % 50 == 0:
                logger.info(f"已提交 {request_id} 请求，当前 QPS≈{request_id / (time.perf_counter() - local.start_time):.2f}")

        for future in as_completed(pending):
            future.result()

    local.end_time = time.perf_counter()
    return local.summary(target_rps=rps)


# ========== 输出 ==========

def _fmt(value, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def print_summary(summary: dict) -> None:
    latency = summary["latency"]
    logger.info("=" * 60)
    logger.info("结果汇总")
    logger.info("=" * 60)
    logger.info(f"请求数: {summary['requests']} | 成功: {summary['success']} | "
                f"失败: {summary['failed']} | 限流: {summary['rate_limited']}")
    logger.info(f"成功率: {summary['success_rate']:.1%} | 墙钟: {_fmt(summary['wall'], 2)}s | "
                f"QPS: {_fmt(summary['qps'], 2)}")
    logger.info(f"延迟: p50 {_fmt(latency['p50'])}s | p90 {_fmt(latency['p90'])}s | "
                f"p99 {_fmt(latency['p99'])}s | mean {_fmt(latency['mean'])}s")
    success_latency = summary.get("latency_success") or {}
    if success_latency.get("n"):
        logger.info(f"成功请求延迟: p50 {_fmt(success_latency['p50'])}s | "
                    f"p99 {_fmt(success_latency['p99'])}s | n={success_latency['n']}")
    if summary["errors"]:
        logger.info(f"错误分布: {summary['errors']}")
    if summary["http_statuses"]:
        logger.info(f"HTTP 状态: {summary['http_statuses']}")


def build_payload(mode: str, summary: dict) -> dict:
    return {
        "meta": {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "base_url": API_BASE_URL,
            "model": MODEL_NAME,
            "mode": mode,
        },
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CSU AI API 速率限制压测")
    parser.add_argument("--mode", choices=["find_limit", "fixed_qps", "single_test"],
                        default="find_limit")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--rps", type=float, default=5.0)
    parser.add_argument("--ladder", default="5,10,20,30,50,100")
    parser.add_argument("--cooldown", type=float, default=30)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--log-dir", default=str(BASE_DIR.parent / "logs"))
    parser.add_argument("--json-out", default="")
    args = parser.parse_args(argv)

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level="INFO",
               format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")
    logger.add(log_dir / "rate_limit_test_{time:YYYY-MM-DD}.log",
               level="DEBUG", rotation="10 MB", encoding="utf-8")

    if not validate_config():
        return 2
    if args.rps <= 0 or args.duration <= 0:
        logger.error("--rps 与 --duration 必须大于 0")
        return 2

    client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL, timeout=args.timeout, max_retries=0)

    if args.mode == "single_test":
        summary = run_concurrent_burst(
            client, MODEL_NAME, args.requests, args.workers or args.requests, args.timeout
        )
        payload = build_payload("single_test", summary)
        print_summary(summary)
    elif args.mode == "fixed_qps":
        summary = fixed_rps(client, MODEL_NAME, args.rps, args.duration, args.workers, args.timeout)
        payload = build_payload("fixed_qps", summary)
        print_summary(summary)
    else:
        ladder = [int(x) for x in args.ladder.split(",") if x.strip()]
        payload = find_limit(
            client, MODEL_NAME, ladder, args.cooldown, args.threshold, args.timeout
        )
        logger.info("\n阶梯结果:")
        logger.info(f"{'并发':<8}{'成功':<8}{'限流':<8}{'成功率':<10}{'p50':<10}{'p99':<10}")
        for row in payload["results"]:
            logger.info(
                f"{row['level']:<8}{row['success']:<8}{row['rate_limited']:<8}"
                f"{row['success_rate']:<10.1%}{_fmt(row['latency']['p50']):<10}"
                f"{_fmt(row['latency']['p99']):<10}"
            )
        logger.info(f"探测到的稳定并发上限: {payload['limit_level']}")

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"JSON: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
