import os
from openai import OpenAI
import json
from fastapi import FastAPI
import dashscope
from math import sqrt, sin, cos  # 数学计算相关
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import traceback
import time
import uuid
from dotenv import load_dotenv
load_dotenv()  # 加载.env文件中的环境变量

# 配置初始化
app = FastAPI(title="工具链调用")

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
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
conversation_history = {}
max_retries=3

# 请求模型
class QueryRequest(BaseModel):
    query: str
    conversation_id: str = None



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
# def handle_tool_call(tool_call):
#     func_name = tool_call.get('function').get('name')
#     args = json.loads(tool_call.get('function').get('arguments'))
#     tool = tool_registry.get(func_name)
#     if tool:
#         return tool["function"](*[args[param] for param in tool["params"]])
#     return "未知工具调用"

# 工具调用处理器
def handle_tool_call(tool_call):
    try:
        func_name = tool_call.get('function', {}).get('name')
        arguments_raw = tool_call.get('function', {}).get('arguments')
        # 健壮性：解析 arguments
        if isinstance(arguments_raw, str):
            try:
                args = json.loads(arguments_raw)
            except json.JSONDecodeError:
                return "参数格式错误（JSON 解析失败）"
        elif isinstance(arguments_raw, dict):
            args = arguments_raw
        else:
            return "参数格式错误（类型不支持）"
        # 查找工具
        tool = tool_registry.get(func_name)
        if not tool:
            return f"未知工具调用：{func_name}"
        # 准备调用参数
        try:
            param_values = [args[param] for param in tool["params"]]
        except KeyError as e:
            return f"缺少必要参数：{e.args[0]}"
        # 调用工具
        return tool["function"](*param_values)
    except Exception as e:
        return f"工具调用失败：{str(e)}"



# 处理工具调用（并支持连续调用）
def process_tool_calls(tool_calls, messages):
    for tool_call in tool_calls:
        result = handle_tool_call(tool_call)
        tool_response = {
            "tool_call_id": tool_call['id'],
            "role": "tool",
            "name": tool_call.get('function').get('name'),
            "content": str(result)
        }
        messages.append(tool_response)



# ================== 对话流程 ==================
# 对话处理函数（支持工具调用失败重试机制）
async def run_conversation(request: QueryRequest):
    query = request.query
    conversation_id = request.conversation_id or await generate_conversation_id()
    #获取当前对话历史（如果不存在则创建）
    messages = conversation_history.setdefault(conversation_id, [])
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": query})

    retries = 0
    while retries < max_retries:
        try:
            # 发起请求
            response = client.chat.completions.create(
                model="qwen-plus-2025-04-28",
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            response_data = json.loads(response.model_dump_json())
            message_data = response_data['choices'][0].get('message', {})

            # 检查是否有工具调用
            tool_calls = message_data.get('tool_calls', [])
            if tool_calls:
                messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
                process_tool_calls(tool_calls,messages)
                # 如果成功调用工具并获得结果，再次调用大模型生成回答
                continue
            else:
                final_reply = message_data.get('content', '')
                messages.append({"role": "assistant", "content": final_reply})
                conversation_history[conversation_id] = messages #保存对话
                return { "answer":final_reply, "conversation_id": conversation_id}  # 如果没有工具调用，返回最终回复

        except Exception as e:
            retries += 1
            print(f"第 {retries} 次重试失败，出错：{str(e)}")
            traceback.print_exc()  # 打印完整的错误堆栈
            if retries >= max_retries:
                return "发生错误，已达到最大重试次数。请稍后再试。"

@app.post("/query")
async def query_endpoint(request: QueryRequest):
    try:
        return await run_conversation(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

