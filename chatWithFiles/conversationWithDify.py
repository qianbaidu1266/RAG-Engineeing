from openai import OpenAI
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


app = FastAPI()

client = OpenAI(
    api_key="sk-e4c8f84ef814473bbb396f5204d179d1",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

model_name = "qwen-plus"
PDF_PATH = "G://AIGC//ChatWithFiles//"

match_pdfs_messages = []
answer_messages = []

# 初始化会话历史字典
match_history = {}
answer_history = {}


DIFY_API_KEY = "app-CM2m8iMljc6jYq8nN8KNIoiu"
DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"

# 定义请求体的 Pydantic 模型
class QueryRequest(BaseModel):
    query: str
    conversation_id: str = None

async def generate_conversation_id():
    """基于时间戳和随机数生成唯一的 conversation_id"""
    timestamp = int(time.time() * 1000)  # 毫秒级时间戳
    random_uuid = uuid.uuid4().hex  # 生成随机 UUID
    return f"{timestamp}_{random_uuid}"


async def read_pdf_with_pdfplumber(file_name):
    """
    异步读取PDF文件，并根据 query 进行段落筛选，避免超出大模型上下文
    """
    loop = asyncio.get_event_loop()  # 获取当前事件循环
    return await loop.run_in_executor(None, read_pdf_sync, file_name)


def read_pdf_sync(file_name):
    """同步读取PDF文件的实现"""
    try:
        file_path = PDF_PATH + file_name
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[0:20]:
                page_text = page.extract_text() or ""
                text += page_text + "\n"

        return text.strip()[:5000]  # 限制最大返回长度

    except FileNotFoundError:
        return f"错误：文件 {file_path} 不存在"
    except Exception as e:
        return f"发生错误：{str(e)}"


async def match_pdfs_with_llm(request: QueryRequest):
    """第一次调用：大模型匹配PDF文件，加入缓存"""
    query = request.query
    conversation_id = request.conversation_id or await generate_conversation_id()
    # 获取当前对话历史（如果不存在则创建）
    messages = match_history.setdefault(conversation_id, [])

    # 1. 读取目录文件
    #files_info = await read_pdf_with_pdfplumber("现行制度体系.pdf")  # 读取目录文件
    files_info = read_pdf_sync("现行制度体系.pdf")
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
        response = await asyncio.to_thread(client.chat.completions.create,
                                           model=model_name,
                                           messages=messages,
                                           temperature=0.7)
        # 4. 解析
        response_data = json.loads(response.model_dump_json())
        data = response_data['choices'][0].get('message', {}).get('content', {})
        messages.append({"role": "assistant", "content": data})
        match_history[conversation_id] = messages #新建或者更新会话记录
        return data
    except json.JSONDecodeError:
        return {"status": "error", "message": "大模型返回格式解析失败"}
    except Exception as e:
        return {"status": "error", "message": f"大模型调用失败: {str(e)}"}




async def async_stream_response(data: dict, request: QueryRequest):
    query = request.query
    conversation_id = request.conversation_id
    files = data.get('matched_files', [])
    relate_info = ""
    for file in files:
        relate_info += file + ":\n" + await read_pdf_with_pdfplumber(file) + "\n\n"
    # **合并参考信息与用户问题**
    combined_query = f"用户问题：{query}\n参考文档信息：\n{relate_info}"
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "inputs": {},
        "query": combined_query,
        "response_mode": "streaming",
        "conversation_id": conversation_id,
        "user": "abc-123",
        "files": []
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", DIFY_API_URL, headers=headers, json=data) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield line + "\n"

    except httpx.HTTPStatusError as e:
        detail = {"status_code": e.response.status_code, "message": e.response.text}
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")



@app.post("/chat")
async def chat_with_files(request: QueryRequest):
    """处理用户问题，并缓存匹配结果"""
    data = await match_pdfs_with_llm(request)
    print("match结果：")
    print(data)
    if isinstance(data, str):
        try:
            data = json.loads(data) # 确保 data 是 JSON 格式
        except json.JSONDecodeError:
            return data
    return StreamingResponse(async_stream_response(data, request), media_type="text/event-stream")


# 使用示例
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)