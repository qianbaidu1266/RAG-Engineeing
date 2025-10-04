import os
import json
from collections import defaultdict
from typing import Dict, List
from openai import OpenAI
from dotenv import load_dotenv
# 加载环境变量
load_dotenv()

# 初始化客户端
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)


# 工具函数实现
def get_current_time() -> str:
    """获取当前时间"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_current_weather(location: str) -> str:
    """模拟天气查询"""
    return f"{location}的天气：晴，25℃"


# 工具注册表
TOOL_REGISTRY = {
    "get_current_time": {
        "function": get_current_time,
        "params": []
    },
    "get_current_weather": {
        "function": get_current_weather,
        "params": ["location"]
    }
}

# 工具定义
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前时间",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "查询指定城市的天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市名称"}
                },
                "required": ["location"]
            }
        }
    }
]


# async def process_stream_response():
#     """处理流式响应核心逻辑"""
#     messages = [
#         {
#             "role": "system",
#             "content": "响应必须包含：\n"
#                        "1. <think>...</think>：详细推理过程\n"
#                        "2. <tool>...</tool>：工具调用（如有）\n"
#                        "3. <answer>...</answer>：最终回答\n"
#                        "即使简单问题也要展示思考！"
#         },
#         {"role": "user", "content": input("请输入问题：")}
#     ]
#     max_retries = 3
#     retries = 0
#     final_answer = None
#     try:
#         while retries < max_retries:
#
#             completion = client.chat.completions.create(
#                 model="qwen-plus-2025-04-28",
#                 messages=messages,
#                 extra_body={"enable_thinking": True},
#                 tools=tools,
#                 parallel_tool_calls=True,
#                 stream=True
#             )
#
#             # 响应数据收集
#             reasoning_content = []
#             answer_content = []
#             tool_info = defaultdict(dict)
#             active_phase = "thinking"  # thinking | answering | tool_calling
#
#             print("*" * 20 + " 思考过程 " + "*" * 20)
#             for chunk in completion:
#                 if not chunk.choices:
#                     continue
#
#                 delta = chunk.choices[0].delta
#
#                 # 处理思考过程（兼容不同字段名）
#                 thinking = getattr(delta, 'reasoning_content', None) or \
#                            getattr(delta, 'thinking_content', None)
#                 if thinking:
#                     if active_phase != "thinking":
#                         active_phase = "thinking"
#                         print("\n" + "=" * 20 + " 思考过程 " + "=" * 20)
#                     reasoning_content.append(thinking)
#                     print(thinking, end="", flush=True)
#
#                 # 处理回复内容
#                 elif delta.content:
#                     if active_phase != "answering":
#                         active_phase = "answering"
#                         print("\n" + "=" * 20 + " 回复内容 " + "=" * 20)
#                     answer_content.append(delta.content)
#                     print(delta.content, end="", flush=True)
#
#                 # 处理工具调用
#                 elif delta.tool_calls:
#                     active_phase = "tool_calling"
#                     for tool_call in delta.tool_calls:
#                         idx = tool_call.index
#
#                         # 收集工具调用ID
#                         if tool_call.id:
#                             tool_info[idx]['id'] = tool_info[idx].get('id', '') + tool_call.id
#
#                         # 处理函数调用信息
#                         if tool_call.function:
#                             # 函数名
#                             if tool_call.function.name:
#                                 tool_info[idx]['name'] = tool_info[idx].get('name', '') + tool_call.function.name
#
#                             # 参数（增量拼接）
#                             if tool_call.function.arguments:
#                                 tool_info[idx]['arguments'] = tool_info[idx].get('arguments',
#                                                                                  '') + tool_call.function.arguments
#                                 try:
#                                     # 实时验证JSON完整性
#                                     json.loads(tool_info[idx]['arguments'])
#                                 except json.JSONDecodeError:
#                                     continue
#
#             # 执行工具调用
#             if tool_info:
#                 print("\n" + "=" * 20 + " 工具调用 " + "=" * 20)
#                 for idx, info in tool_info.items():
#                     try:
#                         func = TOOL_REGISTRY[info['name']]['function']
#                         args = json.loads(info['arguments'])
#                         # 执行工具函数
#                         if info['name'] == "get_current_time":
#                             result = func()
#                         else:
#                             result = func(**args)
#                         print(f"工具 {info['name']} 返回: {result}")
#                     except Exception as e:
#                         print(f"工具调用失败: {str(e)}")
#
#     except Exception as e:
#         retries += 1
#         print(f"\n发生错误: {str(e)}")
#         if 'reasoning_content' in locals():
#             print("已收集的思考过程:", "".join(reasoning_content))


async def process_stream_response():
    """完整的流式响应处理器（修正无工具调用时的输出）"""
    messages = [
        {
            "role": "system",
            "content": "严格按以下格式响应：\n"
                       "1. <think>思考过程</think>\n"
                       "2. <tool_call>工具调用</tool_call>\n"
                       "3. <answer>最终回答</answer>"
        },
        {"role": "user", "content": input("请输入问题：")}
    ]

    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            # 模型请求
            stream = client.chat.completions.create(
                model="qwen-plus-2025-04-28",
                messages=messages,
                extra_body={"enable_thinking": True},
                tools=tools,
                parallel_tool_calls=True,
                stream=True
            )

            # 处理流式响应
            tool_calls = []
            answer_content = []
            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # 思考内容处理
                if delta.content:
                    answer_content.append(delta.content)
                    yield json.dumps({"type": "thinking", "content": delta.content})

                # 收集工具调用
                if delta.tool_calls:
                    tool_calls.extend([{
                        "id": call.id,
                        "name": call.function.name,
                        "args": call.function.arguments or "{}"
                    } for call in delta.tool_calls])
                    for call in delta.tool_calls:
                        yield json.dumps({"type": "tool_call", "name": call.function.name})

            # 情况1：无工具调用时输出最终结果
            if not tool_calls and answer_content:
                yield json.dumps({
                    "type": "answer",
                    "content": "".join(answer_content)
                })
                return

            # 情况2：有工具调用时执行工具
            if tool_calls:
                # 执行工具并更新上下文
                tool_results = []
                for call in tool_calls:
                    try:
                        func = TOOL_REGISTRY[call["name"]]["function"]
                        args = json.loads(call["args"])
                        result = func(**args) if args else func()
                        tool_results.append({
                            "tool_call_id": call["id"],
                            "output": str(result)
                        })
                        yield json.dumps({"type": "tool_result", "name": call["name"], "result": str(result)})
                    except Exception as e:
                        tool_results.append({
                            "tool_call_id": call["id"],
                            "error": str(e)
                        })

                # 更新消息上下文
                messages.extend([
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": call["id"],
                            "function": {"name": call["name"], "arguments": call["args"]}
                        } for call in tool_calls]
                    },
                    {
                        "role": "tool",
                        "content": json.dumps(tool_results)
                    }
                ])

                # 继续处理（可能再次调用工具）
                continue

        except Exception as e:
            retry_count += 1
            yield json.dumps({
                "type": "error",
                "message": f"请求失败（{retry_count}/{max_retries}）：{str(e)}",
                "retryable": retry_count < max_retries
            })
            await asyncio.sleep(1)

    yield json.dumps({
        "type": "error",
        "message": "达到最大重试次数",
        "retryable": False
    })



if __name__ == "__main__":
    import asyncio
    asyncio.run(process_stream_response())