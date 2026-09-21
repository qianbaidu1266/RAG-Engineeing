# ===== file: agent_with_tools.py =====
"""
LangGraph Python 实战：带工具调用的循环 Agent + 持久化记忆
场景：一个能查天气、查订单、查库存的客服 Agent
- 循环调用：Agent 决定是否需要调用工具，调用后继续推理
- 持久化记忆：跨轮对话保持上下文
"""

import os
from typing import Annotated, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode, tools_condition


# ============================================================
# 1. 定义工具
# ============================================================

@tool
def query_weather(city: str) -> str:
    """查询指定城市的天气"""
    # 模拟数据
    weather_db = {
        "北京": "晴天，22°C，空气质量良好",
        "上海": "多云，25°C，有阵雨",
        "深圳": "晴天，30°C，湿度较高",
    }
    return weather_db.get(city, f"暂无{city}的天气数据")


@tool
def query_order(order_id: str) -> str:
    """查询订单状态"""
    order_db = {
        "ORD-001": "已发货，预计3天内到达",
        "ORD-002": "已签收",
        "ORD-003": "待发货，预计明天发出",
    }
    return order_db.get(order_id, f"未找到订单 {order_id}")


@tool
def query_inventory(product_name: str) -> str:
    """查询商品库存"""
    inventory_db = {
        "iPhone 15": "有货，库存 156 件",
        "MacBook Pro": "缺货，预计下周到货",
        "AirPods Pro": "有货，库存 89 件",
    }
    return inventory_db.get(product_name, f"未找到商品 {product_name}")


tools = [query_weather, query_order, query_inventory]


# ============================================================
# 2. 定义 State 与 LLM
# ============================================================

class State(TypedDict):
    messages: Annotated[list, add_messages]


llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,
).bind_tools(tools)  # ✅ 绑定工具到 LLM

SYSTEM_PROMPT = """你是一个智能客服助手「小智」。你可以：
1. 查询城市天气（使用 query_weather 工具）
2. 查询订单状态（使用 query_order 工具）  
3. 查询商品库存（使用 query_inventory 工具）

请根据用户需求选择合适的工具。如果不需要工具，直接回答。"""


# ============================================================
# 3. 定义节点
# ============================================================

def chatbot_node(state: State) -> dict:
    """Agent 主节点：接收消息 → 推理 → 决定调用工具或直接回复"""
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}


# ============================================================
# 4. 构建 Graph（带循环）
# ============================================================

def build_graph():
    """
    循环 Agent Graph：

    START → chatbot → [是否需要工具？]
                        ├── 是 → tools → chatbot → ...（循环）
                        └── 否 → END
    """
    graph = StateGraph(State)

    # 添加节点
    graph.add_node("chatbot", chatbot_node)
    graph.add_node("tools", ToolNode(tools))  # ✅ 使用预构建的 ToolNode

    # 添加边
    graph.add_edge(START, "chatbot")

    # ✅ 条件边：判断 LLM 是否要求调用工具
    graph.add_conditional_edges(
        "chatbot",
        tools_condition,  # 预构建的条件函数：检查最后一条消息是否有 tool_calls
        {
            "tools": "tools",
            "__end__": END,
        }
    )

    # 工具执行完后回到 chatbot 继续推理
    graph.add_edge("tools", "chatbot")

    return graph.compile(checkpointer=MemorySaver())


# ============================================================
# 5. 流式输出辅助函数
# ============================================================

def print_messages(messages: list):
    """美化打印对话历史"""
    for msg in messages:
        role = "👤 Human" if isinstance(msg, HumanMessage) else "🤖 Assistant"
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            print(f"  {role}: [调用工具: {msg.tool_calls}]")
        elif msg.content:
            # 截断太长的内容
            content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
            print(f"  {role}: {content}")


# ============================================================
# 6. 运行
# ============================================================

def main():
    app = build_graph()
    config = {"configurable": {"thread_id": "agent-demo-session"}}

    # 多轮对话
    conversations = [
        "帮我查一下北京的天气",
        "那我查一下我的订单 ORD-001 状态",
        "再查一下 iPhone 15 有没有货",
        "总结一下你帮我查到的信息",  # ✅ 测试记忆能力
    ]

    for user_input in conversations:
        print(f"\n{'=' * 60}")
        print(f"👤 用户: {user_input}")
        print(f"{'=' * 60}")

        result = app.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config,
        )

        # 只打印最新一轮的 Assistant 回复
        last_msg = result["messages"][-1]
        if last_msg.content:
            print(f"🤖 助手: {last_msg.content}")

    # 打印完整对话历史
    print(f"\n{'=' * 60}")
    print("📋 完整对话历史（{0} 条消息）".format(len(result["messages"])))
    print(f"{'=' * 60}")
    print_messages(result["messages"])


if __name__ == "__main__":
    main()
