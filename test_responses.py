#!/usr/bin/env python
# coding=utf-8
"""OpenAI Responses API 连通性测试"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from openai import OpenAI

api_key = os.getenv("API_KEY", "")
base_url = os.getenv("API_BASE_URL", "https://api.chat.csu.edu.cn/v1")
model = os.getenv("MODEL_NAME", "DeepSeek-V4-Flash")

if not api_key:
    print("错误: API_KEY 未设置")
    sys.exit(1)

print(f"API:      OpenAI Responses API")
print(f"Base URL: {base_url}")
print(f"API Key:  {api_key[:12]}...")
print(f"Model:    {model}")
print("正在连接...")

client = OpenAI(api_key=api_key, base_url=base_url)

try:
    response = client.responses.create(
        model=model,
        input="你好，请回复'连通成功'",
        max_output_tokens=100,
    )
    print(f"\n✅ 连通成功!")
    print(f"回复: {response.output_text}")
except AttributeError:
    print(f"\n❌ 当前 openai SDK 版本不支持 responses.create()")
    print(f"   请升级: pip install -U openai")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ 连接失败: {type(e).__name__}: {e}")
    sys.exit(1)
