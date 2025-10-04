# -*- coding: utf-8 -*-
import json
import asyncio
import os
import time
import uuid
from typing import Dict, List, Optional, AsyncGenerator, Union
from threading import Lock
from openai import AsyncOpenAI
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import traceback
import schedule
from dotenv import load_dotenv

load_dotenv()  # 加载.env文件中的环境变量
from contextlib import asynccontextmanager


# 使用 lifespan 管理启动和关闭逻辑
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动逻辑
    start_background_scheduler()
    print("✅ 后台会话清理任务已启动")
    yield  # 应用运行中
    # 关闭逻辑（如果有资源需要清理，可以写在这里）
    print("📴 应用正在关闭...")


# 创建 FastAPI 应用，传入 lifespan
app = FastAPI(lifespan=lifespan)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 从环境变量获取API密钥
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    # 回退机制：仅用于开发和测试环境
    api_key = "your_test_api_key_here"  # 替换为测试密钥

# 使用异步客户端
async_client = AsyncOpenAI(
    api_key=api_key,  # 从环境变量获取
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 安全会话管理
conversation_history: Dict[str, dict] = {}
history_lock = Lock()
max_retries = 3
max_tool_chain_depth = 5  # 最大工具调用链深度


# 请求模型
class QueryRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None


# 辅助函数
async def generate_conversation_id():
    timestamp = int(time.time() * 1000)
    random_uuid = uuid.uuid4().hex
    return f"{timestamp}_{random_uuid}"


# ================== 工具定义 ==================
model_name = "qwen-plus"

system_prompt = """你是一个智能助手，需要根据问题类型选择合适工具获取信息。可用工具包括：
1. 城市编码查询工具（get_city_code）- 根据城市名称查询城市编码
2. 天气查询工具（get_weather）- 根据编码查询所在地的天气情况
3. 天气预测功能（get_weather_forecast）- 根据城市名称预测未来几天的天气情况
回答策略：
1. 主动信息索取：在需要调用城市编码查询等工具功能时，若必要参数（如城市名称）缺失，采用友好且明确的语言主动询问："请问您是想查询哪个城市的天气信息呢？"
2. 精准解答：基于用户提出的问题，严格参照公司政策与操作流程，结合最新文档内容给予精确解答，避免无关扩展，确保用户问题得到有效解决。
3. 透明化操作：在处理用户请求过程中，如需使用特定工具函数，简要告知用户将采取的步骤，增加服务透明度。
4. 确认与跟进：解答完毕后，确认用户是否满意解答，并主动询问是否有其他可以帮助的地方，如："您的问题已解答完毕，请问还有其他方面需要我的帮助吗？"
注意事项：
1.维持专业且亲切的交流风格，确保每一次互动都能提升用户满意度。
2.对于所有工具函数调用，务必确保在获取足够且准确的参数后再执行，避免因信息不全导致处理错误。 
"""


# 工具函数实现
def get_city_code(city_name: str) -> dict:
    city_mapping = {
        "北京": "101010100",
        "上海": "101020100",
        "广州": "101280101",
        "深圳": "101280601",
        "杭州": "101210101",
        "成都": "101270101",
    }
    code = city_mapping.get(city_name, "")
    if not code:
        return {"status": "error", "message": f"找不到城市: {city_name}", "city": city_name}
    return {"status": "success", "code": code, "city": city_name}


def get_weather(city_code: str) -> dict:
    weather_data = {
        "101010100": {"city": "北京", "weather": "晴", "temperature": "10°C"},
        "101020100": {"city": "上海", "weather": "多云", "temperature": "15°C"},
        "101280101": {"city": "广州", "weather": "小雨", "temperature": "20°C"},
        "101280601": {"city": "深圳", "weather": "多云", "temperature": "22°C"},
        "101210101": {"city": "杭州", "weather": "晴", "temperature": "18°C"},
        "101270101": {"city": "成都", "weather": "阴", "temperature": "16°C"},
    }
    result = weather_data.get(city_code)
    if not result:
        return {"status": "error", "message": "无效的城市编码", "code": city_code}
    result["status"] = "success"
    return result


def get_weather_forecast(city_name: str) -> dict:
    forecast_data = {
        "北京": "未来三天：10°C~15°C，晴转多云",
        "上海": "未来三天：15°C~20°C，多云转阴",
        "广州": "未来三天：20°C~25°C，小雨转晴"
    }
    forecast = forecast_data.get(city_name)
    if not forecast:
        return {"status": "error", "message": f"找不到城市: {city_name}", "city": city_name}
    return {"status": "success", "city": city_name, "forecast": forecast}


# 工具注册系统
tool_registry = {}


def register_tool(name: str, func, required_params: list):
    tool_registry[name] = {
        "function": func,
        "required_params": required_params
    }


# 注册工具
register_tool("get_city_code", get_city_code, ["city_name"])
register_tool("get_weather", get_weather, ["city_code"])
register_tool("get_weather_forecast", get_weather_forecast, ["city_name"])


# 工具调用处理器
def handle_tool_call(tool_call: dict) -> dict:
    """处理单个工具调用，返回结构化结果"""
    try:
        # 获取工具名称和参数
        func_name = tool_call["function"]["name"]
        arguments_raw = tool_call["function"].get("arguments", "{}")
        # 解析参数
        if isinstance(arguments_raw, str):
            try:
                args = json.loads(arguments_raw)
            except json.JSONDecodeError:
                args = {"arguments": arguments_raw}
        elif isinstance(arguments_raw, dict):
            args = arguments_raw
        else:
            args = {}
        # 获取工具定义
        tool = tool_registry.get(func_name)
        if not tool:
            return {"status": "error", "message": f"未知工具: {func_name}"}

        # 检查必要参数
        missing_params = [p for p in tool["required_params"] if p not in args]
        if missing_params:
            return {
                "status": "error",
                "message": f"缺少参数: {', '.join(missing_params)}",
                "required_params": tool["required_params"],
                "provided_params": list(args.keys())
            }

        # 执行工具调用
        try:
            # 按参数名称调用
            kwargs = {k: args[k] for k in tool["required_params"]}
            result = tool["function"](**kwargs)
            print(f"🔧 工具调用: {func_name}({kwargs}) => {result}")
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"工具执行失败: {str(e)}",
                "tool": func_name
            }
    except Exception as e:
        return {"status": "error", "message": f"工具调用处理失败: {str(e)}"}


# 处理多个工具调用
def process_tool_calls(tool_calls: List[dict], messages: List[dict]) -> List[dict]:
    """
    处理所有工具调用，并将结果添加到消息历史
    返回工具响应列表
    """
    tool_responses = []
    for tool_call in tool_calls:
        try:
            # 执行工具调用
            result = handle_tool_call(tool_call)
            # 构建工具响应
            tool_response = {
                "tool_call_id": tool_call["id"],
                "role": "tool",
                "name": tool_call["function"]["name"],
                "content": json.dumps(result)  # 结构化结果序列化
            }

            tool_responses.append(tool_response)
            messages.append(tool_response)  # 添加到历史

        except Exception as e:
            error_resp = {
                "tool_call_id": tool_call.get("id", "unknown"),
                "role": "tool",
                "name": tool_call["function"]["name"],
                "content": json.dumps({
                    "status": "error",
                    "message": f"工具调用处理异常: {str(e)}"
                })
            }
            tool_responses.append(error_resp)
            messages.append(error_resp)
    return tool_responses


# ================== 思考步骤解析器 ==================
class ThinkingParser:
    """解析思考步骤的专用工具"""
    THINK_START = "<|thinking|>"
    THINK_END = "<|/thinking|>"

    def __init__(self):
        self.buffer = ""
        self.in_thinking = False
        self.thinking_buffer = ""

    def parse(self, text: str) -> tuple:
        """解析文本并返回(思考内容, 普通内容, 剩余未处理内容)"""
        # 如果文本为空且处于思考状态，强制结束思考
        if not text and self.in_thinking and self.thinking_buffer:
            self.in_thinking = False
            return (self.thinking_buffer, "", "")

        result = []
        self.buffer += text

        while self.buffer:
            if self.in_thinking:
                if self.THINK_END in self.buffer:
                    end_index = self.buffer.index(self.THINK_END)
                    self.thinking_buffer += self.buffer[:end_index]
                    self.buffer = self.buffer[end_index + len(self.THINK_END):]
                    self.in_thinking = False
                    result.append(("think", self.thinking_buffer))
                    self.thinking_buffer = ""
                else:
                    # 未结束标记，缓冲所有内容
                    self.thinking_buffer += self.buffer
                    self.buffer = ""
            else:
                # 寻找思考开始标记
                if self.THINK_START in self.buffer:
                    start_index = self.buffer.index(self.THINK_START)
                    # 获取标记之前的内容作为普通内容
                    before_content = self.buffer[:start_index]
                    if before_content:
                        result.append(("content", before_content))

                    # 移到思考开始标记之后
                    self.buffer = self.buffer[start_index + len(self.THINK_START):]
                    self.in_thinking = True
                    self.thinking_buffer = ""
                else:
                    # 找不到开始标记，全部是普通内容
                    if self.buffer:
                        result.append(("content", self.buffer))
                    self.buffer = ""
                    break

        # 处理剩余缓冲区
        remaining = ""
        if self.buffer and not self.in_thinking:
            remaining = self.buffer
            self.buffer = ""

        # 将结果分类返回
        think_content = "".join([c for t, c in result if t == "think"])
        normal_content = "".join([c for t, c in result if t == "content"])

        return (think_content, normal_content, remaining)

    def flush(self) -> str:
        """强制返回缓冲区剩余内容并重置状态"""
        remaining = self.buffer
        if self.in_thinking:
            remaining = self.THINK_START + self.thinking_buffer + self.buffer

        self.buffer = ""
        self.thinking_buffer = ""
        self.in_thinking = False
        return remaining


# ================== 流式对话核心逻辑 ==================
async def stream_conversation(request: QueryRequest) -> AsyncGenerator[str, None]:
    """流式处理对话的核心函数"""
    query = request.query
    conversation_id = request.conversation_id or await generate_conversation_id()

    # 线程安全地获取或创建会话
    with history_lock:
        messages = conversation_history.setdefault(conversation_id, {
            "id": conversation_id,
            "created_at": int(time.time()),
            "messages": []
        })["messages"]

    # 初始化系统提示
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": system_prompt})

    # 添加用户消息
    user_message = {"role": "user", "content": query}
    messages.append(user_message)

    # 打印用户输入
    print(f"\n{'=' * 50}")
    print(f"💬 用户输入: {query}")
    print(f"📝 会话ID: {conversation_id}")
    print(f"📋 当前消息数: {len(messages)}")

    retries = 0
    tool_chain_depth = 0
    thinking_parser = ThinkingParser()  # 创建思考步骤解析器

    # 事件：会话开始
    start_event = {
        "event": "conversation_start",
        "conversation_id": conversation_id
    }
    print(f"🚀 会话开始")
    yield json.dumps(start_event)

    # 主处理循环
    while retries < max_retries and tool_chain_depth < max_tool_chain_depth:
        tool_chain_depth += 1
        try:
            # 通知模型调用开始
            model_start_event = {
                "event": "model_request_start",
                "conversation_id": conversation_id,
                "depth": tool_chain_depth
            }
            print(f"\n🔄 模型请求开始 (深度: {tool_chain_depth})")
            yield json.dumps(model_start_event)

            # 发起异步流式请求
            print(f"📡 请求模型: {model_name}，消息数: {len(messages)}")
            response_stream = await async_client.chat.completions.create(
                model="qwen-plus-2025-04-28",
                messages=messages,
                extra_body={"enable_thinking": True},  # 确保开启思考步骤
                tools=[{
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": "工具函数",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                # 自动生成参数定义
                                param: {"type": "string"}
                                for param in tool["required_params"]
                            },
                            "required": tool["required_params"]
                        }
                    }
                } for name, tool in tool_registry.items()],
                tool_choice="auto",
                parallel_tool_calls=True,
                stream=True
            )

            content_parts = []
            collected_tool_calls = {}  # {index: tool_call}

            # 流式处理响应
            print("⏳ 接收流式响应...")
            async for chunk in response_stream:
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta
                finish_reason = choice.finish_reason

                # 1. 处理文本内容（包含思考步骤）
                if delta.content:
                    # 解析思考步骤和普通内容
                    content_chunk = delta.content

                    # 打印原始内容片段（调试用）
                    # print(f"原始片段: '{content_chunk}'")

                    # 使用思考解析器处理文本
                    think_text, normal_text, leftover = thinking_parser.parse(content_chunk)

                    # 处理思考步骤
                    if think_text:
                        think_event = {
                            "event": "think",
                            "content": think_text,
                            "conversation_id": conversation_id
                        }
                        # 打印思考内容
                        print(f"\n💭 思考步骤: {think_text}")
                        yield json.dumps(think_event)

                    # 处理普通内容
                    if normal_text:
                        content_event = {
                            "event": "content",
                            "content": normal_text,
                            "conversation_id": conversation_id
                        }
                        # 打印内容片段
                        print(normal_text, end='', flush=True)
                        yield json.dumps(content_event)

                    # 保存到完整内容（无论类型）
                    content_parts.append(content_chunk)

                # 2. 收集工具调用片段
                if delta.tool_calls:
                    for tool_delta in delta.tool_calls:
                        idx = tool_delta.index

                        # 初始化工具调用结构
                        if idx not in collected_tool_calls:
                            collected_tool_calls[idx] = {
                                "id": tool_delta.id or f"toolcall-{uuid.uuid4().hex}",
                                "type": "function",
                                "function": {
                                    "name": "",
                                    "arguments": ""
                                }
                            }

                        # 更新函数名称和参数
                        tool_call = collected_tool_calls[idx]
                        if tool_delta.function.name:
                            tool_call["function"]["name"] = tool_delta.function.name
                        if tool_delta.function.arguments:
                            tool_call["function"]["arguments"] += tool_delta.function.arguments

                # 3. 处理结束原因
                if finish_reason:
                    if content_parts:
                        full_text = "".join(content_parts)
                        messages.append({
                            "role": "assistant",
                            "content": full_text
                        })

                    # 处理工具调用
                    if finish_reason == "tool_calls" and collected_tool_calls:
                        print("\n🛠️ 检测到工具调用请求")
                        break  # 跳出循环处理工具

            # 处理流结束后的剩余思考步骤
            if thinking_parser.thinking_buffer:
                think_event = {
                    "event": "think",
                    "content": thinking_parser.thinking_buffer,
                    "conversation_id": conversation_id
                }
                print(f"\n💭 思考步骤结尾: {thinking_parser.thinking_buffer}")
                yield json.dumps(think_event)
            thinking_parser = ThinkingParser()  # 重置解析器

            # 处理收集到的工具调用
            if collected_tool_calls:
                tool_calls = list(collected_tool_calls.values())

                # 通知工具处理开始
                tool_start_event = {
                    "event": "tool_processing_start",
                    "tool_count": len(tool_calls),
                    "conversation_id": conversation_id
                }
                print(f"\n🔧 开始处理 {len(tool_calls)} 个工具调用")
                yield json.dumps(tool_start_event)

                # 记录工具调用消息
                tool_call_msg = {
                    "role": "assistant",
                    "tool_calls": tool_calls,
                    "content": None
                }
                messages.append(tool_call_msg)

                # 执行工具调用
                tool_responses = process_tool_calls(tool_calls, messages)

                # 流式发送每个工具结果
                for response in tool_responses:
                    result = json.loads(response["content"])
                    tool_result_event = {
                        "event": "tool_result",
                        "tool_name": response["name"],
                        "result": result,
                        "conversation_id": conversation_id
                    }
                    # 打印工具结果
                    print(f"\n✅ 工具结果 [{response['name']}]: {json.dumps(result, ensure_ascii=False, indent=2)}")
                    yield json.dumps(tool_result_event)

                # 重置重试计数器，进入下一轮
                retries = 0
                continue  # 返回循环顶部重新请求模型

            # 没有工具调用，处理最终响应
            elif content_parts:
                full_content = "".join(content_parts)
                messages.append({
                    "role": "assistant",
                    "content": full_content
                })

                # 发送最终完成事件
                complete_event = {
                    "event": "complete",
                    "content": full_content,
                    "conversation_id": conversation_id
                }
                # 打印完整响应
                print(f"\n\n💡 完整响应: {full_content}")
                print(f"data:{json.dumps(complete_event)}\n\n")
                yield json.dumps(complete_event)

                # 保存会话状态
                with history_lock:
                    conversation_history[conversation_id]["messages"] = messages
                    conversation_history[conversation_id]["updated_at"] = int(time.time())

                print(f"✅ 会话完成，消息数: {len(messages)}")
                return  # 结束对话

        except Exception as e:
            retries += 1
            error_msg = f"第 {retries} 次重试失败，错误: {str(e)}"

            # 发送错误事件
            error_event = {
                "event": "error",
                "message": error_msg,
                "conversation_id": conversation_id
            }
            # 打印错误
            print(f"\n❌ 错误: {error_msg}")
            traceback.print_exc()
            yield json.dumps(error_event)

            # 指数退避
            await asyncio.sleep(0.5 * retries)

    # 异常终止处理
    if retries >= max_retries:
        error_msg = "达到最大重试次数，请稍后再试"
        error_event = {
            "event": "error",
            "message": error_msg,
            "conversation_id": conversation_id
        }
        print(f"\n❌ {error_msg}")
        yield json.dumps(error_event)
    elif tool_chain_depth >= max_tool_chain_depth:
        error_msg = "工具调用链过长，已终止会话"
        error_event = {
            "event": "error",
            "message": error_msg,
            "conversation_id": conversation_id
        }
        print(f"\n❌ {error_msg}")
        yield json.dumps(error_event)


# ================== API 端点 ==================
@app.post("/query/stream")
async def stream_query_endpoint(request: QueryRequest):
    """流式查询端点"""
    try:
        print(f"\n{'=' * 50}")
        print(f"🌐 收到新请求: {request.query}")
        if request.conversation_id:
            print(f"🔁 继续会话: {request.conversation_id}")

        return StreamingResponse(
            stream_conversation(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )
    except Exception as e:
        print(f"\n🔥 端点异常: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# 清理过期会话的定时任务
import threading


def clean_expired_conversations():
    """清理过期会话"""
    current_time = time.time()
    expired_keys = []

    with history_lock:
        # 遍历所有会话
        for conv_id, conv_data in conversation_history.items():
            # 30分钟无更新视为过期（1800秒）
            if current_time - conv_data.get("updated_at", 0) > 180:
                expired_keys.append(conv_id)

        # 删除过期会话
        for key in expired_keys:
            del conversation_history[key]
            print(f"🧹 清理过期会话: {key}")
    print(f"🗑️ 清理完成，共删除 {len(expired_keys)} 个过期会话")


# 创建定时任务调度线程
def scheduler_thread():
    """定时任务调度线程"""
    # 每天凌晨两点执行清理
    schedule.every().day.at("11:00:00").do(clean_expired_conversations)
    while True:
        schedule.run_pending()
        time.sleep(60)  # 每分钟检查一次任务


# 在应用启动时启动调度线程
def start_background_scheduler():
    """启动后台定时任务线程"""
    scheduler = threading.Thread(
        target=scheduler_thread,
        name="Conversation Cleaner Scheduler",
        daemon=True  # 设置为守护线程，当主线程退出时自动退出
    )
    scheduler.start()
    return scheduler


# 在FastAPI应用启动时调用
# @app.on_event("startup")
# async def startup_event():
#     start_background_scheduler()
#     print("✅ 后台会话清理任务已启动")

if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("🚀 服务启动中...")
    print(f"🔑 API密钥: {'已设置' if api_key else '未设置'}")
    print(f"🤖 模型名称: {model_name}")
    print(f"🛠️ 注册工具: {', '.join(tool_registry.keys())}")
    print("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=8000)