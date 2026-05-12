#!/usr/bin/env python
# coding=utf-8
"""Anthropic SDK 连通性测试（使用统一的 API_KEY 和 MODEL_NAME）"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from anthropic import Anthropic

api_key = os.getenv("API_KEY", "")
model = os.getenv("MODEL_NAME", "DeepSeek-V4-Flash")

if not api_key:
    print("错误: API_KEY 未设置")
    sys.exit(1)

print(f"SDK:      anthropic")
print(f"API Key:  {api_key[:12]}...")
print(f"Model:    {model}")
print("正在使用 Anthropic SDK 连接 API...")

client = Anthropic(api_key=api_key)

try:
    response = client.messages.create(
        model=model,
        messages=[{"role": "user", "content": "你好，请回复'连通成功'"}],
        max_tokens=100,
    )
    print(f"\n✅ 连通成功!")
    print(f"回复: {response.content[0].text}")
except Exception as e:
    print(f"\n❌ 连接失败: {type(e).__name__}: {e}")
    sys.exit(1)
