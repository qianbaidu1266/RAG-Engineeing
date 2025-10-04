import os
from openai import OpenAI
import json
from fastapi import FastAPI
import dashscope
from math import sqrt, sin, cos  # 数学计算相关
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, List, Any, Optional, AsyncGenerator
import traceback
from openai import AsyncOpenAI, types  # 改用异步客户端
import asyncio
import time
import openai
import uuid

# 配置初始化
app = FastAPI(title="工具链调用-支持流式响应")

client = OpenAI(
    api_key="sk-e4c8f84ef814473bbb396f5204d179d1",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 使用异步客户端
async_client = openai.AsyncOpenAI(
    api_key="sk-e4c8f84ef814473bbb396f5204d179d1",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)


# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

#初始化会话历史记录
conversation_history: Dict[str, List] = {}
max_retries=3

# 请求模型
class QueryRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None



async def generate_conversation_id():
    timestamp = int(time.time() * 1000)
    random_uuid = uuid.uuid4().hex
    return f"{timestamp}_{random_uuid}"


model_name = "qwen-plus"

system_prompt = """你是一个智能助手，需要根据问题类型选择合适工具获取信息。可用工具包括：
1. 城市编码查询工具（get_city_code）- 根据城市名称查询城市编码
2. 天气查询工具（get_weather）- 根据编码查询所在地的天气情况
3. 天气预测功能（get_weather_forecast）- 根据城市名称预测未来几天的天气情况
回答策略：
1. 主动信息索取：在需要调用城市编码查询等工具功能时，若必要参数（如城市名称）缺失，采用友好且明确的语言主动询问：“请问您是想查询哪个城市的天气信息呢？”
2. 精准解答：基于用户提出的问题，严格参照公司政策与操作流程，结合最新文档内容给予精确解答，避免无关扩展，确保用户问题得到有效解决。
3. 透明化操作：在处理用户请求过程中，如需使用特定工具函数，简要告知用户将采取的步骤，增加服务透明度。
4. 确认与跟进：解答完毕后，确认用户是否满意解答，并主动询问是否有其他可以帮助的地方，如：“您的问题已解答完毕，请问还有其他方面需要我的帮助吗？”
注意事项：
1.维持专业且亲切的交流风格，确保每一次互动都能提升用户满意度。
2.对于所有工具函数调用，务必确保在获取足够且准确的参数后再执行，避免因信息不全导致处理错误。 
"""


# ================== 工具函数定义 ==================
def get_city_code(city_name):
    city_mapping = {
        "北京": "101010100",
        "上海": "101020100",
        "广州": "101280101",
    }
    return city_mapping.get(city_name, "未知城市")

def get_weather(city_code):
    weather_data = {
        "101010100": "北京：晴，气温10°C",
        "101020100": "上海：多云，气温15°C",
        "101280101": "广州：小雨，气温20°C",
    }
    return weather_data.get(city_code, "无法获取天气信息")

# 工具调用执行器
def call_tool(tool_name, args):
    if tool_name == "get_city_code":
        return get_city_code(args["city_name"])
    elif tool_name == "get_weather":
        return get_weather(args["city_code"])
    return None


# 定义工具
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_city_code",
            "description": "根据城市名称获取天气查询所需的城市编码",
            "parameters": {
                "type": "object",
                "properties": {
                    "city_name": {
                        "type": "string",
                        "description": "城市名称"
                    }
                },
                "required": ["city_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "根据城市编码获取天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city_code": {
                        "type": "string",
                        "description": "城市编码"
                    }
                },
                "required": ["city_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_forecast",
            "description": "根据城市名预测未来几天的天气情况",
            "parameters": {
                "type": "object",
                "properties": {
                    "city_name": {
                        "type": "string",
                        "description": "城市名称"
                    }
                },
                "required": ["city_name"]
            }
        }
    }
]


# 工具函数
def get_city_code(city_name):
    city_mapping = {
        "北京": "101010100",
        "上海": "101020100",
        "广州": "101280101",
    }
    return city_mapping.get(city_name, "未知城市")


def get_weather(city_code):
    weather_data = {
        "101010100": "北京：晴，气温10°C",
        "101020100": "上海：多云，气温15°C",
        "101280101": "广州：小雨，气温20°C",
    }
    return weather_data.get(city_code, "无法获取天气信息")

def get_weather_forecast(city_name):
    forecast_data = {
        "北京": "未来三天：10°C~15°C，晴转多云",
        "上海": "未来三天：15°C~20°C，多云转阴",
        "广州": "未来三天：20°C~25°C，小雨转晴"
    }
    return forecast_data.get(city_name, "无法获取天气预报")

# 工具注册
tool_registry = {}

def register_tool(name: str, func, params: list):
    tool_registry[name] = {"function": func, "params": params}

# 注册工具
register_tool("get_city_code", get_city_code, ["city_name"])
register_tool("get_weather", get_weather, ["city_code"])
register_tool("get_weather_forecast", get_weather_forecast, ["city_name"])

# ================== 工具调用处理器 ==================
def handle_tool_call(tool_call):
    """执行单个工具调用，支持多种 arguments 格式"""
    try:
        # func_name = tool_call.function.name
        # arguments_raw = tool_call.function.arguments
        func_name = tool_call.get('function', {}).get('name')
        arguments_raw = tool_call.get('function', {}).get('arguments')
        # === 关键优化点：健壮解析 arguments ===
        if isinstance(arguments_raw, str):
            try:
                args = json.loads(arguments_raw)
            except json.JSONDecodeError:
                return "参数格式错误（JSON 解析失败）"
        elif isinstance(arguments_raw, dict):
            args = arguments_raw
        else:
            return "参数格式错误（类型不支持）"
        tool = tool_registry.get(func_name)
        if not tool:
            return f"未知工具调用：{func_name}"
        # 准备参数
        param_values = []
        for param in tool["params"]:
            if param in args:
                param_values.append(args[param])
            elif 'city' in args and param in ['city_name', 'city_code']:
                param_values.append(args['city'])  # 容错：尝试用 'city' 填补参数
            else:
                return f"缺少必要参数: {param}"
        # 工具函数调用
        try:
            result = tool["function"](*param_values)
            return result
        except Exception as e:
            return f"工具执行错误: {str(e)}"
    except AttributeError as ae:
        return f"工具调用结构错误: {str(ae)}"
    except Exception as e:
        return f"工具调用失败: {str(e)}"


# 处理工具调用（并支持连续调用）
def process_tool_calls(tool_calls: List[Dict], messages: List[Dict]) -> List[Dict]:
    """
    处理所有工具调用（流式兼容），并将结果添加到消息历史。
    返回工具响应列表。
    """
    tool_responses = []
    for tool_call in tool_calls:
        try:
            result = handle_tool_call(tool_call)
            tool_response = {
                "tool_call_id": tool_call["id"],
                "role": "tool",
                "name": tool_call["function"]["name"],
                "content": str(result)
            }
            tool_responses.append(tool_response)
            messages.append(tool_response)
        except Exception as e:
            tool_responses.append({
                "tool_call_id": tool_call.get("id", "unknown"),
                "role": "tool",
                "name": tool_call.get("function", {}).get("name", "unknown"),
                "content": f"工具调用失败: {str(e)}"
            })
    return tool_responses


# ================== 流式对话流程 ==================
async def stream_conversation(request: QueryRequest) -> AsyncGenerator[str, None]:
    """流式处理对话的核心函数"""
    query = request.query
    conversation_id = request.conversation_id or await generate_conversation_id()
    messages = conversation_history.setdefault(conversation_id, [])

    # 初始化系统提示
    if not messages:
        messages.append({"role": "system", "content": system_prompt})
    elif messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": system_prompt})

    # 添加用户消息
    messages.append({"role": "user", "content": query})
    retries = 0

    while retries < max_retries:
        try:
            response_stream = await async_client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                stream=True
            )

            collected_tool_calls = []
            content_parts = []
            tool_response_finished = False

            async for chunk in response_stream:
                chunk_dict = chunk.model_dump()
                delta = chunk_dict['choices'][0]['delta']
                finish_reason = chunk_dict['choices'][0]['finish_reason']

                tool_calls_delta = delta.get("tool_calls")
                if isinstance(tool_calls_delta, list):
                    for tool_call in tool_calls_delta:
                        collected_tool_calls.append(tool_call)

                if 'content' in delta:
                    content_parts.append(delta['content'])
                if finish_reason == "tool_calls":
                    break  # 等待收集完工具调用

            if collected_tool_calls:
                yield json.dumps({
                    "event": "tool_response",
                    "tool_name": collected_tool_calls[0]["function"]["name"],
                    "content": "工具调用中...",
                    "conversation_id": conversation_id
                })

                # 记录工具调用消息
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": collected_tool_calls
                })

                # 使用你改造后的 process_tool_calls
                process_tool_calls(collected_tool_calls, messages)
                # 再次触发模型响应
                continue

            # 如果没有工具调用，输出最终响应
            full_content = "".join(content_parts)
            if full_content:
                messages.append({"role": "assistant", "content": full_content})
                yield json.dumps({
                    "event": "complete",
                    "final_content": full_content,
                    "conversation_id": conversation_id
                })
                conversation_history[conversation_id] = messages
                return

        except Exception as e:
            retries += 1
            print(f"[重试 {retries}/{max_retries}] 出错: {str(e)}")
            traceback.print_exc()

        # 达到最大重试次数后返回错误信息
    yield json.dumps({
        "event": "error",
        "message": "多次尝试失败，可能是模型或工具异常。",
        "conversation_id": conversation_id
    })



# ================== API 端点 ==================
@app.post("/query/stream")
async def stream_query_endpoint(request: QueryRequest):
    try:
        return StreamingResponse(
            stream_conversation(request),
            media_type="text/event-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

