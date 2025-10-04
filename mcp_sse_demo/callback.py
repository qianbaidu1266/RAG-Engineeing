import asyncio
import json
from typing import Optional
from contextlib import AsyncExitStack
from fastapi import FastAPI, Request
from pydantic import BaseModel
import openai
from mcp import ClientSession
from fastapi.responses import JSONResponse
from mcp.client.sse import sse_client
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import uuid
import time

load_dotenv()

app = FastAPI()

# 请求结构
class QueryRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None

# 初始化 MCP Client 相关组件
class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.openai = openai.AsyncOpenAI(
            api_key="sk-e4c8f84ef814473bbb396f5204d179d1",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self._streams_context = None
        self._session_context = None
        self.answer_history = {}


    async def connect(self, server_url: str):
        self._streams_context = sse_client(url=server_url)
        streams = await self._streams_context.__aenter__()
        self._session_context = ClientSession(*streams)
        self.session = await self._session_context.__aenter__()
        await self.session.initialize()

    async def cleanup(self):
        if self._session_context:
            await self._session_context.__aexit__(None, None, None)
        if self._streams_context:
            await self._streams_context.__aexit__(None, None, None)

    async def process_messages(self, request: QueryRequest, max_retries: int = 3) -> str:
        conversation_id = request.conversation_id
        messages = self.answer_history.setdefault(conversation_id, [])
        messages.append({"role": "user", "content": request.query})

        tools_response = await self.session.list_tools()
        available_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        } for tool in tools_response.tools]

        retries = 0
        for _ in range(max_retries):
            try:
                response = await self.openai.chat.completions.create(
                    model="qwen-plus",
                    messages=messages,
                    tools=available_tools,
                    tool_choice="auto"
                )
                reply = response.choices[0].message

                # 工具调用分支
                if reply.tool_calls:
                    messages.append({
                        "role": "assistant",
                        "tool_calls": reply.tool_calls,
                        "content": None
                    })

                    for tool_call in reply.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args = json.loads(tool_call.function.arguments)
                        tool_result = await self.session.call_tool(tool_name, tool_args)

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_result.content[0].text
                        })

                    # 工具调用完成后继续调用模型
                    continue

                # 非工具调用：最终回复
                final_reply = reply.content
                messages.append({"role": "assistant", "content": final_reply})
                self.answer_history[conversation_id] = messages
                return final_reply

            except Exception as e:
                retries += 1
                print(f"第 {retries} 次尝试失败: {e}")
                if retries >= max_retries:
                    return f"发生错误：{str(e)}"

        return "工具调用次数已达上限，未生成最终回答。"


def generate_conversation_id():
    timestamp = int(time.time() * 1000)
    random_uuid = uuid.uuid4().hex
    return f"{timestamp}_{random_uuid}"



# 初始化并连接 MCP
mcp_client = MCPClient()

@app.on_event("startup")
async def startup_event():
    await mcp_client.connect("http://0.0.0.0:8020/sse")

@app.on_event("shutdown")
async def shutdown_event():
    await mcp_client.cleanup()

# 请求模型
class ChatRequest(BaseModel):
    query: str
    history: Optional[list[dict]] = []



@app.post("/chat")
async def chat(request: QueryRequest):
    if not request.conversation_id:
        request.conversation_id = generate_conversation_id()
    response_text = await mcp_client.process_messages(request)
    return {
        "conversation_id": request.conversation_id,
        "response": response_text,
        "history": mcp_client.answer_history[request.conversation_id]
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)