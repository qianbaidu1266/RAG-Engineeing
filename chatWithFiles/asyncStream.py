from openai import AsyncClient
import  openai
import pdfplumber
import json
import hashlib
import dashscope
from pydantic import BaseModel
import asyncio
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import uuid
import time
import httpx
from fastapi.middleware.cors import CORSMiddleware

print(openai.__version__)  # 应输出 1.8.0 或更高版本

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（可指定 Dify 服务器地址）
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有请求头
)

async_http_client = httpx.AsyncClient()

client = openai.AsyncOpenAI(
    api_key="sk-e4c8f84ef814473bbb396f5204d179d1",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

model_name = "qwen-plus"
PDF_PATH = "G://AIGC//ChatWithFiles//"

match_pdfs_messages = []
answer_messages = []

# 初始化会话历史字典
match_history = {}
answer_history = {}


class QueryRequest(BaseModel):
    query: str
    conversation_id: str = None

async def generate_conversation_id():
    timestamp = int(time.time() * 1000)
    random_uuid = uuid.uuid4().hex
    return f"{timestamp}_{random_uuid}"

async def read_pdf(file_name):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _sync_read_pdf,
        file_name
    )

def _sync_read_pdf(file_name):
    file_path = PDF_PATH + file_name
    try:
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[:20]:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
        return text[:5000].strip()
    except FileNotFoundError:
        return f"错误：文件 {file_path} 不存在"
    except Exception as e:
        return f"发生错误：{str(e)}"


async def match_pdfs_with_llm(request: QueryRequest):
    """第一次调用：大模型匹配PDF文件，加入缓存"""
    query = request.query
    conversation_id = request.conversation_id
    # 获取当前对话历史（如果不存在则创建）
    messages = match_history.setdefault(conversation_id, [])

    # 1. 读取目录文件
    files_info = await read_pdf("现行制度体系.pdf")  # 读取目录文件
    system_prompt = f"""
    请你根据实际需求查询制度文档的目录信息，分析用户的问题应该查找哪些文档，如果用户的问题不属于目录中的分类，请直接返回无相关分类。
    目录信息：
    {files_info}
    每次回答，你都必须返回严格遵循以下JSON格式的结果，JSON包含以下字段：
    1. matched_files：一个列表，包含最匹配的PDF文件名。
    2. reasoning：一个字符串，包含你匹配文件的理由。
     案例1：
    用户提问：中国的支付体系是怎样的？
    返回：
    {{
     "matched_files":["中国支付体系发展报告2016.pdf"],
     "reasoning":"用户的问题属于支付体系分类。"
    }}
    案例2：
    用户提问：今天天气怎么样？
    返回：
    {{
     "matched_files":[],
     "reasoning":"制度中没有和天气相关的文档信息。"
    }}
    """
    # 确保 system prompt 只添加一次
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": system_prompt})
        # 添加当前用户的提问
    messages.append({"role": "user", "content": query})

    try:
        # 3. 调用大模型
        # 使用异步方式调用模型
        response = await client.chat.completions.create(
                                           model=model_name,
                                           messages=messages,
                                           temperature=0.7,
                                           stream=True  # 启用流式
                                           )
        # 4. 解析
        collected_answer = ""
        async for chunk in response:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if hasattr(delta, "content"):
                content = delta.content
                collected_answer += content
                symbol = "message_end" if choice.finish_reason == "stop" else "message"
                temp = {"event": symbol,"stage":"match","conversation_id": conversation_id,"content": content}
                print(f"response:{temp}")
                # 将字典转换为 JSON 字符串并添加换行符
                yield json.dumps(temp) + "\n"  # 返回字符串类型
            if choice.finish_reason == "stop":
                break # 退出循环，避免重复处理

        # 处理最终结果（在循环结束后）
        try:
            data = json.loads(collected_answer)
        except json.JSONDecodeError:
            data = {"matched_files": []}  # 默认无匹配文件
            messages.append({"role": "assistant", "content": collected_answer})
        else:
            messages.append({"role": "assistant", "content": json.dumps(data)})
        finally:
            match_history[conversation_id] = messages

        # 触发回答阶段（无论是否解析成功）
        if data.get("matched_files"):
            async for answer_chunk in answer_with_llm(data, request):
                yield answer_chunk  # 转发回答阶段的流式响应
    except Exception as e:
        print({"status": "error", "message": f"匹配阶段失败: {str(e)}", "stage": "match"})
        yield json.dumps({"status": "error", "message": f"匹配阶段失败: {str(e)}", "stage": "match"}) + "\n"
    finally:
        # 日志记录（示例）
        print(f"匹配阶段完成，conversation_id={conversation_id}")


async def answer_with_llm(data: dict, request: QueryRequest):
    """第二次调用：读取匹配文档，并调用大模型"""
    query = request.query
    conversation_id = request.conversation_id
    # 获取当前对话历史（如果不存在则创建）
    messages = answer_history.setdefault(conversation_id, [])
    files = data.get('matched_files', [])
    relate_info = ""
    for file in files:
        relate_info += file + ":\n" + await read_pdf(file) + "\n\n"

    # 生成问题+相关文档的提示词
    system_prompt = f"""
    你是一个制度问答智能助手，请根据制度文档参考信息简洁专业地回答用户问题：
    回答策略：
    1.如果制度文档参考信息为空，提示用户没有找到相关的制度文档，引导用户问具体的制度方面的问题。
    2.透明化操作：在处理用户请求过程中，如果参考了制度文档的信息，简要告知用户制度文档的名称，增加信息来源的透明度和可信度。
    3.确认与跟进：解答完毕后，确认用户是否满意解答，并主动询问是否有其他可以帮助的地方，如：“请问还有其他问题需要我的帮助吗？”
    """
    # 确保 system prompt 只添加一次
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": system_prompt})
    # **合并参考信息与用户问题**
    combined_query = f"用户问题：{query}\n参考文档信息：\n{relate_info}"
    # 添加当前用户的提问
    messages.append({"role": "user", "content": combined_query})

    try:
        # 3. 调用大模型
        # 使用异步方式调用模型
        response = await client.chat.completions.create(
                                           model=model_name,
                                           messages=messages,
                                           temperature=0.7,
                                           stream=True  # 启用流式响应
                                           )
        # 4. 解析结果
        answer = ""
        async for chunk in response:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if hasattr(delta, "content"):
                content = delta.content
                answer += content
                if choice.finish_reason == "stop":
                    symbol = "message_end"
                else:
                    symbol = "message"
                temp = {"event": symbol,"stage":"answer","conversation_id": conversation_id,"content": content}
                print(f"response:{temp}")
                # 将字典转换为 JSON 字符串并添加换行符
                yield json.dumps(temp) + "\n"  # 返回字符串类型
            if choice.finish_reason == "stop":
                messages.append({"role": "assistant", "content": answer})
                answer_history[conversation_id] = messages
                break
    except Exception as e:
        yield json.dumps({"status": "error", "message": str(e)})


@app.post("/chat")
async def chat_with_files(request: QueryRequest):
    if not request.conversation_id:
        request.conversation_id = await generate_conversation_id()
    return StreamingResponse(match_pdfs_with_llm(request), media_type="text/event-stream")


# 使用示例
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

