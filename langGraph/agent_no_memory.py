# ===== file: agent_no_memory.py =====
"""
LangGraph Python 实战：无记忆的最简对话 Agent
问题：每次 invoke 都是全新的，LLM "记不住" 之前聊了什么
"""

import os
from typing import Annotated, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


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
    return graph.compile()


def main():
    app = build_graph()

    # ❌ 两次 invoke 互不相关，Agent 完全不记得上一轮
    print("=== 第1轮对话 ===")
    result1 = app.invoke({"messages": [HumanMessage(content="我叫小明，今年25岁")]})
    print(f"Assistant: {result1['messages'][-1].content}\n")

    print("=== 第2轮对话（无记忆，不会记得你是小明）===")
    result2 = app.invoke({"messages": [HumanMessage(content="我叫什么名字？")]})
    print(f"Assistant: {result2['messages'][-1].content}\n")


if __name__ == "__main__":
    main()
