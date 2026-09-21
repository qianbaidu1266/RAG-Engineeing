# ===== file: agent_memory_saver.py =====
"""
LangGraph Python 实战：用 MemorySaver 实现对话记忆
原理：每一步自动保存 State 到 checkpointer，下次按 thread_id 恢复
"""

import os
from typing import Annotated, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver  # ✅ 内存持久化


class State(TypedDict):
    messages: Annotated[list, add_messages]


llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0.7,
)

SYSTEM_PROMPT = """你是一个友好的AI助手，名叫小智。请用简洁的中文回答问题。"""


def chatbot_node(state: State) -> dict:
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}


def build_graph():
    graph = StateGraph(State)
    graph.add_node("chatbot", chatbot_node)
    graph.add_edge(START, "chatbot")
    graph.add_edge("chatbot", END)

    # ✅ 关键差异：compile 时传入 checkpointer
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


def main():
    app = build_graph()

    config = {"configurable": {"thread_id": "user-001-session-1"}}

    # 第1轮
    print("=== 第1轮对话 ===")
    result1 = app.invoke(
        {"messages": [HumanMessage(content="我叫小明，今年25岁")]},
        config=config,
    )
    print(f"Assistant: {result1['messages'][-1].content}\n")

    # 第2轮 ✅ 现在它能记得你了！
    print("=== 第2轮对话（有记忆）===")
    result2 = app.invoke(
        {"messages": [HumanMessage(content="我叫什么名字？今年多大？")]},
        config=config,
    )
    print(f"Assistant: {result2['messages'][-1].content}\n")

    # 第3轮 ✅ 继续累积上下文
    print("=== 第3轮对话 ===")
    result3 = app.invoke(
        {"messages": [HumanMessage(content="总结一下你对我的了解")]},
        config=config,
    )
    print(f"Assistant: {result3['messages'][-1].content}\n")


if __name__ == "__main__":
    main()
