#!/usr/bin/env python
# coding=utf-8
# 这是一个简单的示例，更多使用方法，请查阅openai库的使用.
# https://github.com/openai/openai-python
# 这里的模型都是校内本地的，无法校外调用，也不用担心数据出校.
# 模型有时会因负载过大而崩掉，可以联系高性能计算中心：hpc@csu.edu.cn
# Powered by HPC@csu.edu.cn, 2025.9.10

import os
import time
import json
import sys
from collections import deque
from openai import OpenAI, RateLimitError, APIConnectionError, APIStatusError
from loguru import logger
from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live

console = Console()

# 配置 loguru 日志输出
logger.remove()  # 移除默认 handler
# 控制台输出：显示 INFO 级别及以上
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")
# 文件日志：记录所有 DEBUG 及以上级别，自动轮转
logger.add("logs/ai_chat_{time:YYYY-MM-DD}.log", level="DEBUG", rotation="10 MB", encoding="utf-8")

# ========== 速率限制器 ==========
class RateLimiter:
    """滑动窗口速率限制器"""
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()
    
    def wait_if_needed(self):
        now = time.time()
        # 清理窗口外的请求
        while self.requests and self.requests[0] < now - self.window_seconds:
            self.requests.popleft()
        
        # 如果达到限制，等待
        if len(self.requests) >= self.max_requests:
            wait_time = self.requests[0] + self.window_seconds - now
            if wait_time > 0:
                logger.warning(f"触发速率限制，等待 {wait_time:.2f}s...")
                time.sleep(wait_time)
                # 再次清理
                now = time.time()
                while self.requests and self.requests[0] < now - self.window_seconds:
                    self.requests.popleft()
        
        self.requests.append(time.time())

# 速率限制配置：根据压测结果，10请求内100%成功，20请求开始触发限流
# 设置为 8 请求/60秒，留出安全余量
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX", "10"))
RATE_LIMIT_WINDOW = float(os.getenv("RATE_LIMIT_WINDOW", "60"))
rate_limiter = RateLimiter(RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW)

# ========== 基本配置 ==========
MY_API_KEY = os.getenv("MY_API_KEY")  # 通过环境变量设置 API-KEY
if not MY_API_KEY:
    print("错误: 请设置环境变量 MY_API_KEY")
    sys.exit(1)
API_BASE_URL  = os.getenv("MY_API_BASE", "https://api.chat.csu.edu.cn/v1")

# 初始化 OpenAI 客户端
client = OpenAI(api_key=MY_API_KEY, base_url=API_BASE_URL)

# 初始化使用模型deepseek-v3
MODEL_NAME    = os.getenv("MY_MODEL", "DeepSeek-V4-Flash")

# 要查看更多可用的模型，用下面两行获取。
for model in client.models.list():
    print(f"    -{model.id}")

def ask_model(messages: list) -> str:
    """
    向模型提问并返回答案。
    """
    max_retries = 3
    base_delay = 2
    
    for attempt in range(max_retries):
        try:
            # 速率限制
            rate_limiter.wait_if_needed()
            
            # 调用模型 API
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                max_tokens=1024,
                temperature=0.7,
                stream=True,
          #如果你使用deepseek-v3模型，我们部署的当前版本是V3.1，可以通过以下开关开启思考模式。
          #具体参考https://github.com/sgl-project/sglang/tree/main/benchmark/deepseek_v3
          #开启思考模式后，需要取思考内容，需从resp.choices[0].message.reasoning_content
          #extra_body={"chat_template_kwargs": {"thinking": True}}
            )

            # 性能指标
            start_time = time.time()
            first_token_time = None
            ttft = None  # Time To First Token (秒)
            token_count = 0
            full_response = ""

            # 使用 rich.live 实时渲染 Markdown
            console.print()
            with Live("", console=console, refresh_per_second=10, vertical_overflow="visible") as live:
                for chunk in resp:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        token_count += 1

                        # 记录首字时间
                        if first_token_time is None:
                            first_token_time = time.time()
                            ttft = first_token_time - start_time

                        live.update(Markdown(full_response))
            end_time = time.time()
            total_time = end_time - start_time
            
            # 计算性能指标
            tokens_per_second = token_count / total_time if total_time > 0 else 0
            
            # 记录日志
            logger.info(f"性能指标 | TTFT: {ttft:.3f}s | 总耗时: {total_time:.3f}s | Token数: {token_count} | 生成速率: {tokens_per_second:.2f} tok/s")
            logger.debug(f"完整响应文本长度: {len(full_response)} 字符")

            return full_response.strip() if full_response else "模型没有返回有效的答案。"
            
        except RateLimitError as e:
            # 速率限制错误，等待后重试
            retry_delay = base_delay * (2 ** attempt)
            logger.warning(f"触发 API 速率限制 (尝试 {attempt+1}/{max_retries})，{retry_delay}s 后重试...")
            time.sleep(retry_delay)
            
        except (APIConnectionError, APIStatusError) as e:
            # 其他 API 错误
            logger.error(f"API 请求失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                retry_delay = base_delay * (2 ** attempt)
                time.sleep(retry_delay)
            else:
                return f"调用模型时发生错误: {e}"
                
        except Exception as e:
            return f"调用模型时发生错误: {e}"
    
    return "调用模型失败：超过最大重试次数"

# --- 主程序 ---
if __name__ == "__main__":
    print("--- 开始对话 (输入 /exit 退出) ---")
    
    # 维护对话历史
    messages = [
        {"role": "system", "content": "你是一个有问必答的AI助手。"}
    ]
    
    while True:
        question = input("\n你: ").strip()
        
        if question.lower() == "/exit":
            print("--- 对话结束 ---")
            break
        
        if not question:
            continue
        
        messages.append({"role": "user", "content": question})
        
        answer = ask_model(messages)

        if "调用模型时发生错误" not in answer:
            messages.append({"role": "assistant", "content": answer})
