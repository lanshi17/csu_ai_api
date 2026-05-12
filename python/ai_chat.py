#!/usr/bin/env python
# coding=utf-8
# 这是一个简单的示例，更多使用方法，请查阅各 SDK 的使用文档.
# OpenAI: https://github.com/openai/openai-python
# Anthropic: https://github.com/anthropics/anthropic-sdk-python
# 这里的模型都是校内本地的，无法校外调用，也不用担心数据出校.
# 模型有时会因负载过大而崩掉，可以联系高性能计算中心：hpc@csu.edu.cn
# Powered by HPC@csu.edu.cn, 2025.9.10

import os
import time
import sys
from abc import ABC, abstractmethod
from collections import deque
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live

# 加载 .env 文件
load_dotenv(Path(__file__).parent / ".env")

console = Console()

# 配置 loguru 日志输出
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")
logger.add("../logs/ai_chat_{time:YYYY-MM-DD}.log", level="DEBUG", rotation="10 MB", encoding="utf-8")


# ========== 速率限制器 ==========
class RateLimiter:
    """滑动窗口速率限制器"""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()

    def wait_if_needed(self):
        now = time.time()
        while self.requests and self.requests[0] < now - self.window_seconds:
            self.requests.popleft()

        if len(self.requests) >= self.max_requests:
            wait_time = self.requests[0] + self.window_seconds - now
            if wait_time > 0:
                logger.warning(f"触发速率限制，等待 {wait_time:.2f}s...")
                time.sleep(wait_time)
                now = time.time()
                while self.requests and self.requests[0] < now - self.window_seconds:
                    self.requests.popleft()

        self.requests.append(time.time())


# ========== 配置 ==========
class Config:
    """从环境变量读取配置"""

    PROVIDER = os.getenv("API_PROVIDER", "openai").lower()
    API_KEY = os.getenv("API_KEY", "")
    API_BASE_URL = os.getenv("API_BASE_URL", "https://api.chat.csu.edu.cn/v1")
    MODEL_NAME = os.getenv("MODEL_NAME", "DeepSeek-V4-Flash")
    SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "你是一个有问必答的AI助手。")
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
    RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "10"))
    RATE_LIMIT_WINDOW = float(os.getenv("RATE_LIMIT_WINDOW", "60"))

    @classmethod
    def validate(cls):
        if not cls.API_KEY:
            logger.error("请设置 API_KEY 环境变量")
            sys.exit(1)


# ========== 抽象客户端 ==========
class AIClient(ABC):
    """AI 客户端抽象基类"""

    def __init__(self, config: type[Config]):
        self.config = config
        self.rate_limiter = RateLimiter(config.RATE_LIMIT_MAX, config.RATE_LIMIT_WINDOW)

    @abstractmethod
    def list_models(self) -> list[str]:
        """列出可用模型"""
        ...

    @abstractmethod
    def chat_stream(self, messages: list[dict]):
        """流式对话，返回生成器"""
        ...


# ========== OpenAI 客户端 ==========
class OpenAIClient(AIClient):
    """OpenAI 及 OpenAI 兼容 API 客户端"""

    def __init__(self, config: type[Config]):
        super().__init__(config)
        from openai import OpenAI

        self.client = OpenAI(api_key=config.API_KEY, base_url=config.API_BASE_URL)
        self.model = config.MODEL_NAME

    def list_models(self) -> list[str]:
        return [model.id for model in self.client.models.list()]

    def chat_stream(self, messages: list[dict]):
        self.rate_limiter.wait_if_needed()
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.config.MAX_TOKENS,
            temperature=self.config.TEMPERATURE,
            stream=True,
        )


# ========== Anthropic 客户端 ==========
class AnthropicClient(AIClient):
    """Anthropic Claude 客户端（使用统一的 API_KEY 和 MODEL_NAME）"""

    def __init__(self, config: type[Config]):
        super().__init__(config)
        from anthropic import Anthropic

        self.client = Anthropic(api_key=config.API_KEY)
        self.model = config.MODEL_NAME

    def list_models(self) -> list[str]:
        # Anthropic SDK 没有 models.list()，返回已知模型列表
        return [
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
        ]

    def chat_stream(self, messages: list[dict]):
        self.rate_limiter.wait_if_needed()

        # 分离 system message
        system_prompt = ""
        filtered_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                filtered_messages.append(msg)

        return self.client.messages.create(
            model=self.model,
            messages=filtered_messages,
            system=system_prompt,
            max_tokens=self.config.MAX_TOKENS,
            temperature=self.config.TEMPERATURE,
            stream=True,
        )


# ========== 客户端工厂 ==========
def create_client(config: type[Config]) -> AIClient:
    """根据配置创建对应的客户端"""
    providers = {
        "openai": OpenAIClient,
        "anthropic": AnthropicClient,
    }

    provider = config.PROVIDER
    if provider not in providers:
        logger.error(f"不支持的提供商: {provider}，支持的提供商: {list(providers.keys())}")
        sys.exit(1)

    logger.info(f"使用提供商: {provider}")
    return providers[provider](config)


# ========== 核心逻辑 ==========
def ask_model(client: AIClient, messages: list[dict]) -> str:
    """向模型提问并返回答案"""
    max_retries = 3
    base_delay = 2

    for attempt in range(max_retries):
        try:
            resp = client.chat_stream(messages)

            start_time = time.time()
            first_token_time = None
            ttft = None
            token_count = 0
            full_response = ""

            console.print()
            with Live("", console=console, refresh_per_second=10, vertical_overflow="visible") as live:
                if isinstance(client, OpenAIClient):
                    for chunk in resp:
                        if chunk.choices and chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            full_response += content
                            token_count += 1
                            if first_token_time is None:
                                first_token_time = time.time()
                                ttft = first_token_time - start_time
                            live.update(Markdown(full_response))
                elif isinstance(client, AnthropicClient):
                    for chunk in resp:
                        if chunk.type == "content_block_delta":
                            content = chunk.delta.text
                            full_response += content
                            token_count += 1
                            if first_token_time is None:
                                first_token_time = time.time()
                                ttft = first_token_time - start_time
                            live.update(Markdown(full_response))

            end_time = time.time()
            total_time = end_time - start_time
            tokens_per_second = token_count / total_time if total_time > 0 else 0

            logger.info(
                f"性能指标 | TTFT: {ttft:.3f}s | 总耗时: {total_time:.3f}s | Token数: {token_count} | 生成速率: {tokens_per_second:.2f} tok/s"
            )
            logger.debug(f"完整响应文本长度: {len(full_response)} 字符")

            return full_response.strip() if full_response else "模型没有返回有效的答案。"

        except Exception as e:
            error_type = type(e).__name__
            if "RateLimit" in error_type or "rate_limit" in str(e).lower():
                retry_delay = base_delay * (2**attempt)
                logger.warning(f"触发 API 速率限制 (尝试 {attempt+1}/{max_retries})，{retry_delay}s 后重试...")
                time.sleep(retry_delay)
            elif "Connection" in error_type or "API" in error_type:
                logger.error(f"API 请求失败 (尝试 {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    retry_delay = base_delay * (2**attempt)
                    time.sleep(retry_delay)
                else:
                    return f"调用模型时发生错误: {e}"
            else:
                return f"调用模型时发生错误: {e}"

    return "调用模型失败：超过最大重试次数"


# ========== 主程序 ==========
if __name__ == "__main__":
    Config.validate()

    client = create_client(Config)

    # 列出可用模型
    logger.info("可用模型列表:")
    try:
        for model_id in client.list_models():
            print(f"    - {model_id}")
    except Exception as e:
        logger.warning(f"无法获取模型列表: {e}")

    print(f"\n当前使用模型: {client.model if hasattr(client, 'model') else Config.MODEL_NAME}")
    print("--- 开始对话 (输入 /exit 退出) ---")

    messages = [{"role": "system", "content": Config.SYSTEM_PROMPT}]

    while True:
        question = input("\n你: ").strip()

        if question.lower() == "/exit":
            print("--- 对话结束 ---")
            break

        if not question:
            continue

        messages.append({"role": "user", "content": question})
        answer = ask_model(client, messages)

        if "调用模型时发生错误" not in answer and "调用模型失败" not in answer:
            messages.append({"role": "assistant", "content": answer})
