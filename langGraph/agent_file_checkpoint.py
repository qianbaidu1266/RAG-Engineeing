# ===== file: agent_file_checkpoint.py =====
"""
LangGraph Python 实战：FileSystemCheckpointSaver 文件持久化
- 适合单实例部署
- 进程重启后对话记录不丢失
"""

import os
from typing import Annotated, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # SQLite 持久化
import aiosqlite


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


async def build_graph_async():
    """异步构建 Graph，因为 SqliteSaver 需要 async 连接"""
    graph = StateGraph(State)
    graph.add_node("chatbot", chatbot_node)
    graph.add_edge(START, "chatbot")
    graph.add_edge("chatbot", END)

    # ✅ SQLite 文件持久化
    conn = aiosqlite.connect("chat_checkpoints.db")
    db = await conn.as_conn()
    checkpointer = AsyncSqliteSaver.from_conn_string("chat_checkpoints.db")
    await checkpointer.setup()

    return graph.compile(checkpointer=checkpointer)


def build_graph_sync():
    """
    同步版本：使用 SqliteSaver（非 async）
    适合简单脚本使用
    """
    from langgraph.checkpoint.sqlite import SqliteSaver

    graph = StateGraph(State)
    graph.add_node("chatbot", chatbot_node)
    graph.add_edge(START, "chatbot")
    graph.add_edge("chatbot", END)

    # ✅ SQLite 文件持久化（同步版）
    checkpointer = SqliteSaver.from_conn_string("chat_checkpoints.db")
    return graph.compile(checkpointer=checkpointer)


def main():
    app = build_graph_sync()

    config = {"configurable": {"thread_id": "persistent-session-001"}}

    print("=== 第1轮（文件持久化）===")
    r = app.invoke({"messages": [HumanMessage(content="记住：我住在上海，爱好是摄影")]}, config=config)
    print(f"Assistant: {r['messages'][-1].content}\n")

    print("=== 第2轮（即使重启进程，也能恢复）===")
    r = app.invoke({"messages": [HumanMessage(content="我住在哪里？有什么爱好？")]}, config=config)
    print(f"Assistant: {r['messages'][-1].content}\n")

    print("✅ checkpoint 数据已保存到 chat_checkpoints.db")
    print("   重启进程后，使用相同 thread_id 即可恢复完整对话历史")


if __name__ == "__main__":
    main()
