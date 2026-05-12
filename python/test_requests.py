#!/usr/bin/env python
# coding=utf-8
"""使用 requests 库测试 API 连通性"""

import os
import sys
import time
import json
from pathlib import Path

from dotenv import load_dotenv
import requests

load_dotenv(Path(__file__).parent / ".env")

api_key = os.getenv("API_KEY", "")
base_url = os.getenv("API_BASE_URL", "https://api.chat.csu.edu.cn/v1")
model = os.getenv("MODEL_NAME", "DeepSeek-V4-Flash")

if not api_key:
    print("错误: API_KEY 未设置")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

print(f"Method:   requests (HTTP)")
print(f"Base URL: {base_url}")
print(f"API Key:  {api_key[:12]}...")
print(f"Model:    {model}")


def test_chat_completions():
    """测试 Chat Completions API"""
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "你好，请回复'连通成功'"}],
        "max_tokens": 100,
        "stream": True,
    }

    print("\n--- Chat Completions (stream=True) ---")
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30, stream=True)
        resp.raise_for_status()

        full_text = ""
        start = time.time()
        first_token = None

        for line in resp.iter_lines():
            if line:
                text = line.decode("utf-8")
                if text.startswith("data: ") and text != "data: [DONE]":
                    chunk = json.loads(text[6:])
                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if content:
                        if first_token is None:
                            first_token = time.time() - start
                        full_text += content
                        print(content, end="", flush=True)

        elapsed = time.time() - start
        print(f"\n✅ 成功 | TTFT: {first_token:.3f}s | 总耗时: {elapsed:.3f}s")
        return True

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP {e.response.status_code}: {e.response.text}")
    except Exception as e:
        print(f"\n❌ {type(e).__name__}: {e}")
    return False


def test_chat_completions_non_stream():
    """测试非流式 Chat Completions"""
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "你好，请回复'连通成功'"}],
        "max_tokens": 100,
        "stream": False,
    }

    print("\n--- Chat Completions (stream=False) ---")
    try:
        start = time.time()
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        elapsed = time.time() - start

        content = data["choices"][0]["message"]["content"]
        print(f"回复: {content}")
        print(f"✅ 成功 | 耗时: {elapsed:.3f}s | Tokens: {data.get('usage', {}).get('total_tokens', 'N/A')}")
        return True

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP {e.response.status_code}: {e.response.text}")
    except Exception as e:
        print(f"\n❌ {type(e).__name__}: {e}")
    return False


def test_models_list():
    """测试 Models 列表"""
    url = f"{base_url}/models"

    print("\n--- Models List ---")
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = [m["id"] for m in data.get("data", [])]
        print(f"可用模型 ({len(models)} 个):")
        for m in sorted(models):
            print(f"  - {m}")
        print("✅ 成功")
        return True

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP {e.response.status_code}: {e.response.text}")
    except Exception as e:
        print(f"\n❌ {type(e).__name__}: {e}")
    return False


if __name__ == "__main__":
    results = {
        "Models List": test_models_list(),
        "Chat Completions (非流式)": test_chat_completions_non_stream(),
        "Chat Completions (流式)": test_chat_completions(),
    }

    print("\n" + "=" * 50)
    print("测试汇总:")
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")

    if not all(results.values()):
        sys.exit(1)
