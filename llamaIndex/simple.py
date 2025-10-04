from fastapi import FastAPI, Body, HTTPException
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI
import json
import pdfplumber
import asyncio
import os
from typing import Dict, Any
from pydantic import BaseModel
import uuid
import time
import pandas as pd
from openai import OpenAI
import json


app = FastAPI()

client = OpenAI(
    api_key="sk-e4c8f84ef814473bbb396f5204d179d1",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

model_name = "qwen-plus"

answer_history = {}


# 定义请求体的 Pydantic 模型
class QueryRequest(BaseModel):
    query: str
    conversation_id: str = None

async def generate_conversation_id():
    """基于时间戳和随机数生成唯一的 conversation_id"""
    timestamp = int(time.time() * 1000)  # 毫秒级时间戳
    random_uuid = uuid.uuid4().hex  # 生成随机 UUID
    return f"{timestamp}_{random_uuid}"


# ============ Excel 问答加载 ============
def load_qa_from_excel(file_path: str):
    df = pd.read_excel(file_path)
    qa_pairs = list(zip(df['问题'], df['答案']))
    return qa_pairs


qa_pairs = load_qa_from_excel("G://AIGC//ChatWithFiles//xlsx//FAQ.xlsx")


async def chat_with_llm(request: QueryRequest):
    query = request.query
    if not request.conversation_id:
        request.conversation_id = await generate_conversation_id()
    conversation_id = request.conversation_id
    # 获取当前对话历史（如果不存在则创建）
    messages = answer_history.setdefault(conversation_id, [])

    system_prompt = f"""
     你是一个自助验证业务联调平台的智能客服助手，请根据参考信息简洁专业地回答用户问题：
     参考信息：""" + str(qa_pairs) + """
     回答策略：
     1.如果没有用户问题对应的参考信息，提示用户没有找到的参考信息，引导用户问具体的业务联调方面的问题。
     2.透明化操作：在处理用户请求过程中，如果参考了的信息，简要告知用户制度文档的名称，增加信息来源的透明度和可信度。
     3.确认与跟进：解答完毕后，确认用户是否满意解答，并主动询问是否有其他可以帮助的地方，如：“请问还有其他问题需要我的帮助吗？”
     """
    # 2. 构造提示词
    # 确保 system prompt 只添加一次
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": system_prompt})
        # 添加当前用户的提问
    messages.append({"role": "user", "content": query})

    try:
        # 1. 验证输入
        if not query.strip():
            raise ValueError("问题内容不能为空")

        # 3. 调用大模型
        response = await asyncio.to_thread(client.chat.completions.create,
                                           model=model_name,
                                           messages=messages,
                                           temperature=0.7)
        # 4. 解析结果
        response_data = json.loads(response.model_dump_json())
        answer = response_data['choices'][0].get('message', {}).get('content', {})
        messages.append({"role": "assistant", "content": answer})
        answer_history[conversation_id] = messages  # 新建或者更新会话记录
        print("answer_history:")
        print(answer_history)
        return {"answer": answer, "conversation_id": conversation_id}
    except json.JSONDecodeError:
        return {"status": "error", "message": "大模型返回格式解析失败"}
    except Exception as e:
        return {"status": "error", "message": f"大模型调用失败: {str(e)}"}



@app.post("/chat")
async def chat_with_files(request: QueryRequest):
    return await chat_with_llm( request)

# 使用示例
if __name__ == "__main__":

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

