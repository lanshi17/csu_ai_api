#!/usr/bin/env python
# coding=utf-8
"""
API 速率限制压测脚本
用于测试供应商的请求频率限制上限
"""

import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from openai import OpenAI, RateLimitError, APIConnectionError, APIStatusError
from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")
logger.add("logs/rate_limit_test_{time:YYYY-MM-DD}.log", level="DEBUG", rotation="10 MB", encoding="utf-8")

# ========== 基本配置 ==========
MY_API_KEY = os.getenv("MY_API_KEY")
if not MY_API_KEY:
    logger.error("请设置环境变量 MY_API_KEY")
    sys.exit(1)
API_BASE_URL = os.getenv("MY_API_BASE", "https://api.chat.csu.edu.cn/v1")
MODEL_NAME = os.getenv("MY_MODEL", "DeepSeek-V4-Flash")

client = OpenAI(api_key=MY_API_KEY, base_url=API_BASE_URL)

# ========== 测试结果统计 ==========
class TestStats:
    def __init__(self):
        self.lock = threading.Lock()
        self.total_requests = 0
        self.success_count = 0
        self.failed_count = 0
        self.rate_limited_count = 0
        self.start_time = None
        self.end_time = None
        self.response_times = []
        self.requests_timeline = deque()  # (timestamp, success/fail)
    
    def record_success(self, response_time: float):
        with self.lock:
            self.success_count += 1
            self.total_requests += 1
            self.response_times.append(response_time)
            self.requests_timeline.append((time.time(), "success"))
    
    def record_rate_limit(self):
        with self.lock:
            self.rate_limited_count += 1
            self.failed_count += 1
            self.total_requests += 1
            self.requests_timeline.append((time.time(), "rate_limited"))
    
    def record_error(self):
        with self.lock:
            self.failed_count += 1
            self.total_requests += 1
            self.requests_timeline.append((time.time(), "error"))

stats = TestStats()

def make_request(request_id: int) -> dict:
    """发送单次请求"""
    start = time.time()
    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": f"压测请求 #{request_id}，请简短回复ok"}],
            max_tokens=20,
            temperature=0.1,
            stream=False
        )
        response_time = time.time() - start
        stats.record_success(response_time)
        return {"id": request_id, "status": "success", "time": response_time}
    except RateLimitError as e:
        response_time = time.time() - start
        stats.record_rate_limit()
        return {"id": request_id, "status": "rate_limited", "time": response_time}
    except (APIConnectionError, APIStatusError) as e:
        response_time = time.time() - start
        stats.record_error()
        return {"id": request_id, "status": "error", "time": response_time, "error": str(e)}
    except Exception as e:
        response_time = time.time() - start
        stats.record_error()
        return {"id": request_id, "status": "error", "time": response_time, "error": str(e)}

def run_concurrent_test(num_requests: int, max_workers: int):
    """运行并发测试"""
    logger.info(f"开始压测: {num_requests} 个请求, {max_workers} 并发线程")
    stats.start_time = time.time()
    
    success_results = []
    failed_results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(make_request, i) for i in range(num_requests)]
        
        for future in as_completed(futures):
            result = future.result()
            if result["status"] == "success":
                success_results.append(result)
            else:
                failed_results.append(result)
    
    stats.end_time = time.time()
    total_time = stats.end_time - stats.start_time
    
    # 打印结果
    logger.info("=" * 60)
    logger.info("压测结果")
    logger.info("=" * 60)
    logger.info(f"总请求数: {stats.total_requests}")
    logger.info(f"成功: {stats.success_count}")
    logger.info(f"失败: {stats.failed_count}")
    logger.info(f"速率限制: {stats.rate_limited_count}")
    logger.info(f"总耗时: {total_time:.2f}s")
    logger.info(f"平均 QPS: {stats.total_requests / total_time:.2f}")
    
    if success_results:
        avg_time = sum(r["time"] for r in success_results) / len(success_results)
        min_time = min(r["time"] for r in success_results)
        max_time = max(r["time"] for r in success_results)
        logger.info(f"成功请求平均响应时间: {avg_time:.3f}s")
        logger.info(f"成功请求最小响应时间: {min_time:.3f}s")
        logger.info(f"成功请求最大响应时间: {max_time:.3f}s")
    
    return stats

def find_rate_limit():
    """
    自动查找速率限制上限
    使用递增并发策略
    """
    logger.info("开始自动探测速率限制...")
    
    # 测试配置
    test_configs = [
        (5, 5),
        (10, 10),
        (20, 20),
        (30, 30),
        (50, 50),
        (100, 50),
    ]
    
    results = []
    
    for num_requests, max_workers in test_configs:
        logger.info(f"\n--- 测试配置: {num_requests} 请求, {max_workers} 并发 ---")
        
        # 重置统计
        global stats
        stats = TestStats()
        
        run_concurrent_test(num_requests, max_workers)
        
        success_rate = stats.success_count / stats.total_requests if stats.total_requests > 0 else 0
        results.append({
            "requests": num_requests,
            "workers": max_workers,
            "success": stats.success_count,
            "failed": stats.failed_count,
            "rate_limited": stats.rate_limited_count,
            "success_rate": success_rate,
        })
        
        # 等待一段时间避免被限流影响下一次测试
        logger.info("等待 30s 后继续下一轮测试...")
        time.sleep(30)
    
    # 打印总结
    logger.info("\n" + "=" * 80)
    logger.info("压测总结")
    logger.info("=" * 80)
    logger.info(f"{'请求数':<10} {'并发数':<10} {'成功':<10} {'失败':<10} {'限流':<10} {'成功率':<10}")
    logger.info("-" * 80)
    for r in results:
        logger.info(
            f"{r['requests']:<10} {r['workers']:<10} {r['success']:<10} "
            f"{r['failed']:<10} {r['rate_limited']:<10} {r['success_rate']*100:.1f}%"
        )

def continuous_rps_test(duration_seconds: int, target_rps: float):
    """
    持续固定 QPS 测试
    """
    logger.info(f"开始持续 QPS 测试: {target_rps} 请求/秒, 持续 {duration_seconds} 秒")
    
    stats.start_time = time.time()
    interval = 1.0 / target_rps
    request_id = 0
    
    with ThreadPoolExecutor(max_workers=int(target_rps * 2)) as executor:
        while time.time() - stats.start_time < duration_seconds:
            loop_start = time.time()
            futures = [executor.submit(make_request, request_id)]
            request_id += 1
            
            for future in as_completed(futures):
                pass  # 结果已记录在 stats 中
            
            # 控制请求速率
            elapsed = time.time() - loop_start
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    total_time = time.time() - stats.start_time
    
    logger.info("=" * 60)
    logger.info("持续 QPS 测试结果")
    logger.info("=" * 60)
    logger.info(f"目标 QPS: {target_rps}")
    logger.info(f"实际 QPS: {stats.total_requests / total_time:.2f}")
    logger.info(f"总请求: {stats.total_requests}")
    logger.info(f"成功: {stats.success_count}")
    logger.info(f"失败: {stats.failed_count}")
    logger.info(f"限流: {stats.rate_limited_count}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="API 速率限制压测工具")
    parser.add_argument(
        "--mode",
        choices=["find_limit", "fixed_qps", "single_test"],
        default="find_limit",
        help="压测模式"
    )
    parser.add_argument("--requests", type=int, default=20, help="单次测试请求数")
    parser.add_argument("--workers", type=int, default=20, help="并发线程数")
    parser.add_argument("--duration", type=int, default=60, help="持续测试时间(秒)")
    parser.add_argument("--rps", type=float, default=5.0, help="目标 QPS")
    
    args = parser.parse_args()
    
    if args.mode == "find_limit":
        find_rate_limit()
    elif args.mode == "fixed_qps":
        continuous_rps_test(args.duration, args.rps)
    elif args.mode == "single_test":
        run_concurrent_test(args.requests, args.workers)
