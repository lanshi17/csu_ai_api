#!/usr/bin/env python
# coding=utf-8
"""测试 JSON mode 和 LangGraph 强制结构化输出"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).parent / ".env")

from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

api_key = os.getenv("API_KEY", "")
base_url = os.getenv("API_BASE_URL", "https://api.chat.csu.edu.cn/v1")
model = os.getenv("MODEL_NAME", "DeepSeek-V4-Flash")

if not api_key:
    print("错误: API_KEY 未设置")
    sys.exit(1)

print(f"Base URL: {base_url}")
print(f"API Key:  {api_key[:12]}...")
print(f"Model:    {model}")


# ========== 测试 1: OpenAI JSON mode ==========
def test_openai_json_mode():
    """测试 OpenAI response_format=json_object"""
    print("\n" + "=" * 50)
    print("测试 1: OpenAI JSON mode (response_format)")
    print("=" * 50)
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)

        start = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个JSON生成器，只返回合法的JSON。"},
                {
                    "role": "user",
                    "content": "生成一个用户信息，包含 name(张三), age(25), email(zhangsan@example.com)，返回JSON格式。",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=500,
        )
        elapsed = time.time() - start

        content = response.choices[0].message.content
        print(f"原始响应:\n{content}")

        # 验证是否为合法 JSON
        parsed = json.loads(content)
        print(f"\n✅ JSON 解析成功!")
        print(f"解析结果: {json.dumps(parsed, indent=2, ensure_ascii=False)}")
        print(f"耗时: {elapsed:.3f}s")
        return True

    except json.JSONDecodeError as e:
        print(f"\n❌ JSON 解析失败: {e}")
        print(f"原始内容: {content}")
        return False
    except Exception as e:
        print(f"\n❌ {type(e).__name__}: {e}")
        return False


# ========== 测试 2: OpenAI JSON Schema mode ==========
def test_openai_json_schema():
    """测试 OpenAI 带 schema 的 JSON mode"""
    print("\n" + "=" * 50)
    print("测试 2: OpenAI JSON Schema mode")
    print("=" * 50)
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)

        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "user_info",
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "age": {"type": "integer"},
                        "email": {"type": "string"},
                        "hobbies": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["name", "age", "email", "hobbies"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }

        start = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个JSON生成器，严格按照schema返回。"},
                {
                    "role": "user",
                    "content": "生成一个用户信息，姓名李四，年龄30，邮箱lisi@example.com，爱好包括读书、游泳、编程。",
                },
            ],
            response_format=schema,
            temperature=0,
            max_tokens=500,
        )
        elapsed = time.time() - start

        content = response.choices[0].message.content
        print(f"原始响应:\n{content}")

        parsed = json.loads(content)
        print(f"\n✅ JSON Schema 模式成功!")
        print(f"解析结果: {json.dumps(parsed, indent=2, ensure_ascii=False)}")
        print(f"耗时: {elapsed:.3f}s")
        return True

    except json.JSONDecodeError as e:
        print(f"\n❌ JSON 解析失败: {e}")
        print(f"原始内容: {content}")
        return False
    except Exception as e:
        print(f"\n❌ {type(e).__name__}: {e}")
        return False


# ========== 测试 3: LangGraph 强制结构化输出 ==========
class UserInfo(BaseModel):
    """用户信息 Pydantic 模型"""
    name: str = Field(description="用户姓名")
    age: int = Field(description="用户年龄")
    email: str = Field(description="用户邮箱")
    hobbies: List[str] = Field(description="用户爱好列表")


def test_langgraph_structured_output():
    """测试 LangGraph + with_structured_output 强制结构化输出
    
    注意：LangGraph 的 MessagesState 不支持直接存储 Pydantic 对象。
    有两种解决方案：
    1. 在节点内将结构化结果转为 AIMessage
    2. 使用自定义 State 而非 MessagesState
    这里采用方案 1。
    """
    print("\n" + "=" * 50)
    print("测试 3: LangGraph 强制结构化输出 (with_structured_output)")
    print("=" * 50)
    try:
        from langgraph.graph import StateGraph, MessagesState, START, END
        from langchain_core.messages import AIMessage

        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            max_tokens=500,
        )

        # 使用 with_structured_output 强制结构化输出
        structured_llm = llm.with_structured_output(UserInfo)

        def chatbot(state: MessagesState):
            result = structured_llm.invoke(state["messages"])
            # 将 Pydantic 对象转为 AIMessage，保持 MessagesState 兼容
            if isinstance(result, BaseModel):
                json_str = result.model_dump_json()
                return {"messages": [AIMessage(content=json_str)]}
            return {"messages": [result]}

        graph_builder = StateGraph(MessagesState)
        graph_builder.add_node("chatbot", chatbot)
        graph_builder.add_edge(START, "chatbot")
        graph_builder.add_edge("chatbot", END)
        graph = graph_builder.compile()

        start = time.time()
        result = graph.invoke(
            {
                "messages": [
                    SystemMessage(content="你是一个数据生成器，按要求返回结构化数据。"),
                    HumanMessage(
                        content="生成一个用户信息：姓名王五，年龄28，邮箱wangwu@example.com，爱好包括跑步、音乐、旅行。"
                    ),
                ]
            }
        )
        elapsed = time.time() - start

        last_msg = result["messages"][-1]
        print(f"消息类型: {type(last_msg)}")

        content = last_msg.content
        print(f"原始内容:\n{content}")

        # 解析 JSON 并验证
        parsed = json.loads(content)
        user_info = UserInfo(**parsed)
        print(f"\n✅ LangGraph 结构化输出成功!")
        print(f"姓名: {user_info.name}")
        print(f"年龄: {user_info.age}")
        print(f"邮箱: {user_info.email}")
        print(f"爱好: {', '.join(user_info.hobbies)}")
        print(f"耗时: {elapsed:.3f}s")
        return True

    except json.JSONDecodeError as e:
        print(f"\n❌ JSON 解析失败: {e}")
        return False
    except Exception as e:
        print(f"\n❌ {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


# ========== 测试 4: LangGraph 直接返回 Pydantic 对象 ==========
def test_langgraph_pydantic_direct():
    """测试 LangGraph 直接返回 Pydantic 对象（不使用 graph）"""
    print("\n" + "=" * 50)
    print("测试 4: LangChain with_structured_output 直接调用")
    print("=" * 50)
    try:
        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            max_tokens=500,
        )

        structured_llm = llm.with_structured_output(UserInfo)

        start = time.time()
        result = structured_llm.invoke(
            [
                SystemMessage(content="你是一个数据生成器。"),
                HumanMessage(
                    content="生成用户信息：姓名赵六，年龄35，邮箱zhaoliu@example.com，爱好包括摄影、烹饪、骑行。"
                ),
            ]
        )
        elapsed = time.time() - start

        print(f"返回类型: {type(result)}")
        print(f"结果: {result}")

        if isinstance(result, UserInfo):
            print(f"\n✅ 直接返回 Pydantic 对象成功!")
            print(f"姓名: {result.name}")
            print(f"年龄: {result.age}")
            print(f"邮箱: {result.email}")
            print(f"爱好: {', '.join(result.hobbies)}")
            print(f"耗时: {elapsed:.3f}s")
            return True
        elif isinstance(result, dict):
            user_info = UserInfo(**result)
            print(f"\n✅ 返回 dict，转换为 Pydantic 成功!")
            print(f"姓名: {user_info.name}")
            print(f"年龄: {user_info.age}")
            print(f"邮箱: {user_info.email}")
            print(f"爱好: {', '.join(user_info.hobbies)}")
            print(f"耗时: {elapsed:.3f}s")
            return True
        else:
            # 可能是 AIMessage，尝试解析 content
            if hasattr(result, "content"):
                parsed = json.loads(result.content)
                user_info = UserInfo(**parsed)
                print(f"\n✅ 从 AIMessage 解析成功!")
                print(f"姓名: {user_info.name}")
                print(f"年龄: {user_info.age}")
                print(f"邮箱: {user_info.email}")
                print(f"爱好: {', '.join(user_info.hobbies)}")
                print(f"耗时: {elapsed:.3f}s")
                return True
            else:
                print(f"❌ 无法识别的返回类型: {type(result)}")
                return False

    except Exception as e:
        print(f"\n❌ {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    results = {
        "OpenAI JSON mode": test_openai_json_mode(),
        "OpenAI JSON Schema mode": test_openai_json_schema(),
        "LangGraph 结构化输出": test_langgraph_structured_output(),
        "LangChain 直接结构化调用": test_langgraph_pydantic_direct(),
    }

    print("\n" + "=" * 50)
    print("测试汇总:")
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")

    if not all(results.values()):
        sys.exit(1)
