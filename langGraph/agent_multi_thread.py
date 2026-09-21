# ===== file: agent_multi_thread.py =====
"""
LangGraph Python 实战：多用户 / 多会话隔离
不同 thread_id 的对话完全独立，互不干扰
"""

import os
from typing import Annotated, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver


class State(TypedDict):
    messages: Annotated[list, add_messages]


llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0.7,
)

SYSTEM_PROMPT = """你是一个友好的AI助手。请用简洁的中文回答。"""


def chatbot_node(state: State) -> dict:
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}


def build_graph():
    graph = StateGraph(State)
    graph.add_node("chatbot", chatbot_node)
    graph.add_edge(START, "chatbot")
    graph.add_edge("chatbot", END)
    return graph.compile(checkpointer=MemorySaver())


def main():
    app = build_graph()

    # ===== 用户A 的会话 =====
    config_a = {"configurable": {"thread_id": "user-alice-session-1"}}
    print("=== 用户 Alice 第1轮 ===")
    r = app.invoke({"messages": [HumanMessage(content="我喜欢的颜色是蓝色")]}, config=config_a)
    print(f"Assistant: {r['messages'][-1].content}\n")

    # ===== 用户B 的会话（完全独立）=====
    config_b = {"configurable": {"thread_id": "user-bob-session-1"}}
    print("=== 用户 Bob 第1轮 ===")
    r = app.invoke({"messages": [HumanMessage(content="我是Bob，我养了一只猫")]}, config=config_b)
    print(f"Assistant: {r['messages'][-1].content}\n")

    # ===== 回到用户A（上下文完好）=====
    print("=== 用户 Alice 第2轮（回到Alice的会话）===")
    r = app.invoke({"messages": [HumanMessage(content="我喜欢什么颜色？")]}, config=config_a)
    print(f"Assistant: {r['messages'][-1].content}\n")

    # ===== 回到用户B（上下文完好，完全不知道Alice的事）=====
    print("=== 用户 Bob 第2轮（回到Bob的会话）===")
    r = app.invoke({"messages": [HumanMessage(content="你喜欢什么颜色？我的宠物是什么？")]}, config=config_b)
    print(f"Assistant: {r['messages'][-1].content}\n")


if __name__ == "__main__":
    main()
