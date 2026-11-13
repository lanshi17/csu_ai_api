#!/usr/bin/env python
# coding=utf-8
"""合并多次 benchmark 报告（例如因网关限流而分模型运行）。

重算分位数与吞吐阈值后输出统一的 JSON / Markdown，便于写文档。

用法：
    uv run merge_reports.py --inputs results/deepseek/*.json results/glm/*.json \
        --output-md results/merged.md --output-json results/merged.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import bench_metrics as bm
import benchmark as B


def _normalize_sample(raw: dict[str, Any]) -> bm.Sample:
    """按当前阈值重算速率指标，避免旧报告残留异常 tok/s。"""
    sample = dict(raw)
    tokens = sample.get("completion_tokens")
    if sample.get("stream"):
        tps, tpot = B._rate_metrics(tokens, sample.get("gen_duration"))
        sample["tps"], sample["tpot"] = tps, tpot
    elif tokens:
        latency = sample.get("latency")
        if latency:
            sample["tps"] = tokens / latency
            sample["tpot"] = latency / tokens
    return bm.Sample(**sample)


def merge(reports: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not reports:
        raise ValueError("至少需要一个报告")

    base = reports[0]
    base_url = base["meta"]["base_url"]
    version = base["meta"]["dataset_version"]
    summaries: list[bm.CaseSummary] = []
    models: list[str] = []
    model_repeat: dict[str, int] = {}
    concurrency: list[dict[str, Any]] = []

    for report in reports:
        meta = report["meta"]
        if meta["base_url"] != base_url or meta["dataset_version"] != version:
            raise ValueError("报告的 base_url 或数据集版本不一致")
        for model in meta["models"]:
            if model not in models:
                models.append(model)
                model_repeat[model] = meta["repeat"]
        for item in report["summaries"]:
            samples = [_normalize_sample(sample) for sample in item["samples"]]
            # 保持模型名来自报告，避免 embedding/rerank 的用例级模型串台
            summaries.append(bm.summarize_samples(samples))
        concurrency.extend(report.get("concurrency") or [])

    meta = dict(base["meta"])
    meta.update(
        {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "models": models,
            "repeat": max(model_repeat.values()),
            "model_repeat": model_repeat,
            "case_count": len({s.case_id for s in summaries}),
        }
    )
    for key in ("reasoning_effort", "min_interval", "timeout", "stream"):
        for report in reports:
            value = report["meta"].get(key)
            if value not in (None, "", "-"):
                meta[key] = value
                break

    return {
        "meta": meta,
        "dimensions_meta": base.get("dimensions_meta", {}),
        "summaries": [s.to_dict() for s in summaries],
        "dimensions": bm.aggregate_dimensions(summaries),
        "concurrency": concurrency,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合并 benchmark JSON 报告")
    parser.add_argument("--inputs", nargs="+", required=True, help="输入 JSON 报告")
    parser.add_argument("--output-md", default="", help="输出 Markdown 路径")
    parser.add_argument("--output-json", default="", help="输出合并 JSON 路径")
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.inputs]
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    merged = merge(reports)
    merged["meta"]["merged_from"] = [str(p) for p in paths]

    md_path = Path(args.output_md) if args.output_md else paths[0].with_name("merged.md")
    json_path = (
        Path(args.output_json) if args.output_json else paths[0].with_name("merged.json")
    )
    B.write_markdown(merged, md_path)
    B.write_json(merged, json_path)

    print(f"合并 {len(reports)} 份报告，模型: {', '.join(merged['meta']['models'])}")
    print(f"Markdown: {md_path}")
    print(f"JSON: {json_path}")
    B.print_report(merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
