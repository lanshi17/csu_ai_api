#!/usr/bin/env python
# coding=utf-8
"""使用 LangGraph + LangChain-OpenAI 测试 API 连通性"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv(Path(__file__).parent / ".env")

api_key = os.getenv("API_KEY", "")
base_url = os.getenv("API_BASE_URL", "https://api.chat.csu.edu.cn/v1")
model = os.getenv("MODEL_NAME", "DeepSeek-V4-Flash")

if not api_key:
    print("错误: API_KEY 未设置")
    sys.exit(1)

print(f"SDK:      LangGraph + LangChain-OpenAI")
print(f"Base URL: {base_url}")
print(f"API Key:  {api_key[:12]}...")
print(f"Model:    {model}")


def test_invoke():
    """测试同步调用"""
    print("\n--- invoke() 同步调用 ---")
    try:
        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.7,
            max_tokens=100,
        )

        start = time.time()
        messages = [
            SystemMessage(content="你是一个有问必答的AI助手。"),
            HumanMessage(content="你好，请回复'连通成功'"),
        ]
        response = llm.invoke(messages)
        elapsed = time.time() - start

        print(f"回复: {response.content}")
        print(f"✅ 成功 | 耗时: {elapsed:.3f}s | Tokens: {response.usage_metadata}")
        return True

    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
        return False


def test_stream():
    """测试流式调用"""
    print("\n--- stream() 流式调用 ---")
    try:
        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.7,
            max_tokens=100,
            streaming=True,
        )

        start = time.time()
        first_token = None
        full_text = ""

        messages = [
            SystemMessage(content="你是一个有问必答的AI助手。"),
            HumanMessage(content="你好，请回复'连通成功'"),
        ]

        for chunk in llm.stream(messages):
            content = chunk.content
            if content:
                if first_token is None:
                    first_token = time.time() - start
                full_text += content
                print(content, end="", flush=True)

        elapsed = time.time() - start
        ttft = first_token if first_token else 0
        print(f"\n✅ 成功 | TTFT: {ttft:.3f}s | 总耗时: {elapsed:.3f}s")
        return True

    except Exception as e:
        print(f"\n❌ {type(e).__name__}: {e}")
        return False


def test_langgraph():
    """测试 LangGraph 简单链"""
    print("\n--- LangGraph 简单链 ---")
    try:
        from langgraph.graph import StateGraph, MessagesState, START, END

        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.7,
            max_tokens=100,
        )

        def chatbot(state: MessagesState):
            return {"messages": [llm.invoke(state["messages"])]}

        graph_builder = StateGraph(MessagesState)
        graph_builder.add_node("chatbot", chatbot)
        graph_builder.add_edge(START, "chatbot")
        graph_builder.add_edge("chatbot", END)
        graph = graph_builder.compile()

        start = time.time()
        result = graph.invoke(
            {"messages": [HumanMessage(content="你好，请回复'连通成功'")]},
        )
        elapsed = time.time() - start

        last_msg = result["messages"][-1]
        print(f"回复: {last_msg.content}")
        print(f"✅ LangGraph 成功 | 耗时: {elapsed:.3f}s")
        return True

    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    results = {
        "invoke() 同步调用": test_invoke(),
        "stream() 流式调用": test_stream(),
        "LangGraph 简单链": test_langgraph(),
    }

    print("\n" + "=" * 50)
    print("测试汇总:")
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")

    if not all(results.values()):
        sys.exit(1)
