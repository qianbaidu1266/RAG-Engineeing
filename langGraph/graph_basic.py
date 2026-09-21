# ===== file: graph_basic.py =====
"""
LangGraph Python 实战：基于 State、Node、Edge 手写第一个可运行 Graph
场景：带条件分支的「智能客服」（售前/售后分流）
"""

import os
from typing import Annotated, TypedDict
from typing_extensions import TypedDict as ExtTypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


# ============================================================
# 1. 定义 State（状态结构）
# ============================================================
class CustomerServiceState(TypedDict):
    """客服系统的全局状态"""
    # messages: 用 add_messages 作为 reducer，自动追加而非覆盖
    messages: Annotated[list, add_messages]
    # 分类结果：pre_sales | after_sales
    category: str
    # 最终回复
    answer: str


# ============================================================
# 2. 初始化 LLM
# ============================================================
llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,
)


# ============================================================
# 3. 定义节点函数
# ============================================================

def classify_node(state: CustomerServiceState) -> dict:
    """
    分类节点：根据用户问题，判断是「售前」还是「售后」
    使用结构化输出确保返回标准分类
    """
    question = state["messages"][-1].content if state["messages"] else ""

    prompt = f"""你是一个客服分类助手。请根据用户的问题，判断它属于以下哪一类：

- "pre_sales"：产品咨询、价格、功能对比、购买建议等售前问题
- "after_sales"：退换货、维修、使用故障、发票等售后问题

用户问题：{question}

请只返回分类关键词（pre_sales 或 after_sales），不要输出其他内容。"""

    response = llm.invoke([HumanMessage(content=prompt)])
    category = response.content.strip().lower()

    # ✅ 健壮处理：如果 LLM 返回的内容不完全匹配，做一次映射
    if "pre" in category:
        category = "pre_sales"
    else:
        category = "after_sales"

    print(f"  📋 分类结果: {category}")
    return {"category": category}


def pre_sales_node(state: CustomerServiceState) -> dict:
    """售前回复节点"""
    question = state["messages"][-1].content

    prompt = f"""你是一个专业的售前客服。请针对用户的咨询给出详细、热情的回复。
    可以介绍产品优势、价格方案、适用场景等。

    用户问题：{question}"""

    response = llm.invoke([HumanMessage(content=prompt)])
    answer = response.content
    print(f"  🛒 [售前回复]: {answer[:80]}...")
    return {"answer": answer, "messages": [response]}


def after_sales_node(state: CustomerServiceState) -> dict:
    """售后回复节点"""
    question = state["messages"][-1].content

    prompt = f"""你是一个耐心的售后服务人员。请针对用户的问题给出解决方案。
    涉及退换货请说明流程，涉及故障请给出排查步骤。

    用户问题：{question}"""

    response = llm.invoke([HumanMessage(content=prompt)])
    answer = response.content
    print(f"  🔧 [售后回复]: {answer[:80]}...")
    return {"answer": answer, "messages": [response]}


# ============================================================
# 4. 构建条件路由函数
# ============================================================

def route_by_category(state: CustomerServiceState) -> str:
    """根据分类结果决定走哪个分支"""
    category = state.get("category", "pre_sales")
    if category == "pre_sales":
        return "pre_sales"
    else:
        return "after_sales"


# ============================================================
# 5. 组装 Graph
# ============================================================

def build_graph():
    """
    构建完整的客服 Graph：

    START → classify_node → [条件分支]
                              ├── pre_sales → END
                              └── after_sales → END
    """
    graph = StateGraph(CustomerServiceState)

    # 添加节点
    graph.add_node("classify", classify_node)
    graph.add_node("pre_sales", pre_sales_node)
    graph.add_node("after_sales", after_sales_node)

    # 添加边
    graph.add_edge(START, "classify")

    # ✅ 关键：条件边必须带映射表
    graph.add_conditional_edges(
        "classify",
        route_by_category,
        {
            "pre_sales": "pre_sales",
            "after_sales": "after_sales",
        }
    )

    graph.add_edge("pre_sales", END)
    graph.add_edge("after_sales", END)

    return graph.compile()


# ============================================================
# 6. 运行
# ============================================================

def main():
    app = build_graph()

    # 测试用例
    test_questions = [
        "你们的Pro版和标准版有什么区别？价格分别是多少？",
        "我上周买的设备突然无法开机了，怎么处理？",
    ]

    for question in test_questions:
        print(f"\n{'=' * 60}")
        print(f"👤 用户提问: {question}")
        print(f"{'=' * 60}")

        result = app.invoke({
            "messages": [HumanMessage(content=question)],
            "category": "",
            "answer": "",
        })

        print(f"\n✅ 最终回复: {result['answer'][:120]}...")
        print(f"   分类: {result['category']}")


if __name__ == "__main__":
    main()
