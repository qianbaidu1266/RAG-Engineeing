from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.responses import StreamingResponse
import json
import httpx
import os
import requests
from pydantic import BaseModel

app = FastAPI()


DIFY_API_KEY = "app-CM2m8iMljc6jYq8nN8KNIoiu"
DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"


class StreamRequest(BaseModel):
    """请求体模型"""
    query: str
    conversation_id: str = ""  # 允许空字符串，默认会话ID


@app.post("/stream")
def stream_dify_response(data: StreamRequest)-> StreamingResponse:
    """
    返回原始流式响应生成器

    参数：
    user_query: str - 用户问题（必需）
    api_key: str - API密钥
    conversation_id: str - 会话ID
    user_id: str - 用户标识
    files: list - 文件列表

    返回：
    generator - 生成原始流式数据块
    """
    query = data.query
    conversation_id = data.conversation_id

    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "inputs": {},
        "query": query,
        "response_mode": "streaming",
        "conversation_id": conversation_id,
        "user": "test",
        "files":  []
    }

    try:
        response = requests.post(
            DIFY_API_URL,
            headers=headers,
            json=payload,
            stream=True
        )
        response.raise_for_status()

        # 使用 FastAPI 的 StreamingResponse 处理流式响应
        def generate():
            for line in response.iter_lines():
                if line:
                    # Add a newline after each line of the response content
                    yield line.decode('utf-8') + "\n"

        # 使用 FastAPI 的 StreamingResponse 处理流式响应
        return StreamingResponse(
            content = generate(),
            media_type="text/event-stream"
        )

    except requests.exceptions.HTTPError as e:
        # Dify API 返回的 HTTP 错误（如 400、401）
        detail = {
            "status_code": e.response.status_code,
            "message": e.response.text
        }
        raise HTTPException(
            status_code=e.response.status_code,
            detail=detail
        )
    except Exception as e:
        # 网络错误或其他异常
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )



def stream_response(query: str, conversation_id: str = ""):
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "inputs": {},
        "query": query,
        "response_mode": "streaming",
        "conversation_id": conversation_id,
        "user": "abc-123",
        "files": []
    }
    try:
        response = requests.post(DIFY_API_URL, headers=headers, json=data, stream=True)
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                yield line.decode("utf-8") + "\n"
    except requests.exceptions.HTTPError as e:
        detail = {"status_code": e.response.status_code, "message": e.response.text}
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


async def async_stream_response(query: str, conversation_id: str = ""):
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "inputs": {},
        "query": query,
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
async def chat_stream(request: StreamRequest):
    return StreamingResponse(async_stream_response(request.query, request.conversation_id), media_type="text/event-stream")



# 启动 FastAPI 时的流式响应支持
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)