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
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（可指定 Dify 服务器地址）
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有请求头
)

client = OpenAI(
    api_key="sk-e4c8f84ef814473bbb396f5204d179d1",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

model_name = "qwen-plus"
PDF_PATH = "G://AIGC//ChatWithFiles//"

# 初始化会话历史字典
conversation_history = {}

DIFY_API_KEY = "app-CM2m8iMljc6jYq8nN8KNIoiu"
DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"

# 定义请求体的 Pydantic 模型
class QueryRequest(BaseModel):
    query: str
    conversation_id: str = None

class FileRequest(BaseModel):
    file_name: str

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
    return await loop.run_in_executor(None, read_pdf, file_name)


def read_pdf(file_list):
    """同步读取PDF文件的实现"""
    try:
        text = ""
        for fileName in file_list:
            file_path = PDF_PATH + fileName
            text = text + fileName + "的内容:\n"
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages[0:20]:
                    page_text = page.extract_text() or ""
                    text += page_text + "\n"
            text = text.encode('utf-8', 'ignore').decode('utf-8')
        return text.strip()[:10000]  # 限制最大返回长度
    except FileNotFoundError:
        return f"错误：文件 {file_path} 不存在"
    except Exception as e:
        return f"发生错误：{str(e)}"


# ================== 工具声明 ==================
tools = [
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": "根据文件名读取文件内容，并返回文件内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_list": {"type": "[]", "description": "文件名称列表"}
                },
                "required": ["file_list"]
            }
        }
    }]

# ================== 工具调用处理器 ==================
def handle_tool_call(tool_call):
    func_name = tool_call.get('function').get('name')
    args = json.loads(tool_call.get('function').get('arguments'))
    if func_name == "read_pdf":
        return read_pdf(**args)
    else:
        return "未知工具调用"

async def match_pdfs_with_llm(request: QueryRequest):
    """第一次调用：大模型匹配PDF文件，加入缓存"""
    query = request.query
    conversation_id = request.conversation_id or await generate_conversation_id()
    # 获取当前对话历史（如果不存在则创建）
    messages = conversation_history.setdefault(conversation_id, [])

    system_prompt = f"""
    你是一个制度问答智能助手，请根据制度文档参考信息简洁专业地回答用户问题。请你根据实际需求查询制度文档的目录信息，分析用户的问题应该查找哪些制度文档，然后调用工具读取制度文档信息，根据制度文档信息的内容回答用户问题。
    如果用户的问题不属于目录中的分类，提示用户没有找到相关的制度文档，引导用户问具体的制度方面的问题。
    目录信息：
    {{
    "支付体系":["中国支付体系发展报告2016.pdf"],
    "反洗钱":["2022年中国反洗钱报告.pdf"],
    "金融稳定":["中国金融稳定报告2017.pdf", "中国金融稳定报告2016.pdf"],
    "货币政策":["2024年第四季度中国货币政策执行报告.pdf","2024年第一季度中国货币政策执行报告.pdf"],
    }}
    可用工具：
    工具名称：read_pdf
    工具描述：根据PDF文件名读取PDF文件内容，并返回文件内容。
    工具参数：
    - file_list: 文件名列表，类型为字符串数组，必填。
    工具返回：
    - 文件内容，类型为字符串。
    工具示例：
    输入：read_pdf(["示例1.pdf","示例2.pdf"])
    输出：文件内容
    回答策略：
    1.如果制度文档参考信息为空，提示用户没有找到相关的制度文档，引导用户问具体的制度方面的问题。
    2.透明化操作：在处理用户请求过程中，如果参考了制度文档的信息，简要告知用户制度文档的名称，增加信息来源的透明度和可信度。
    3.确认与跟进：解答完毕后，确认用户是否满意解答，并主动询问是否有其他可以帮助的地方，如：“请问还有其他问题需要我的帮助吗？”
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
                                           tools=tools,
                                           tool_choice="auto",
                                           temperature=0.7)
        # 4. 解析
        response_data = json.loads(response.model_dump_json())
        tools_cal = response_data['choices'][0].get('message', {}).get('tool_calls', [])

        # 处理所有工具调用
        tool_responses = []
        if isinstance(tools_cal, list):  # 确保 message 是列表
            for tool_call in tools_cal:
                # print("tool_call:")
                # print(tool_call)  # 打印工具调用的整个字典
                # print("type of tool_call:", type(tool_call))  # 打印类型，确保是字典
                # print("function key exists:", 'function' in tool_call)  # 确保字典中有 'function' 键
                # print("function structure:", tool_call.get('function').get('name'))  # 打印 'function' 部分
                result = handle_tool_call(tool_call)
                tool_responses.append({
                    "tool_call_id": tool_call['id'],
                    "role": "tool",
                    "name": tool_call.get('function').get('name'),
                    "content": str(result)
                })
        else:
            # 处理没有工具调用的情况
            print("No tool calls found in message.")

        # 只有在工具调用不为空时，才记录工具调用响应
        if tool_responses:
            messages.append({"role": "assistant", "content": None, "tool_calls": tools_cal})
            messages.extend(tool_responses)


        # 第二次调用：生成最终回答
        second_response = await asyncio.to_thread(client.chat.completions.create,
                                model = model_name,
                                messages = messages,
                                tools = tools,
                                temperature = 0.7)
        data = second_response.choices[0].message.content
        messages.append({"role": "assistant", "content": data})
        conversation_history[conversation_id] = messages #新建或者更新会话记录
        print("conversation_history:")
        print(conversation_history)
        return {"answer": data, "conversation_id": conversation_id}
    except json.JSONDecodeError:
        return {"status": "error", "message": "大模型返回格式解析失败"}
    except Exception as e:
        e.with_traceback()
        return {"status": "error", "message": f"大模型调用失败: {str(e)}"}


@app.post("/chat")
async def chat_with_files(request: QueryRequest):
    """处理用户问题，并缓存匹配结果"""
    data = await match_pdfs_with_llm(request)
    print("match结果：")
    print(data)
    return data


@app.post("/file")
def get_files(file: FileRequest):
    return read_pdf(file.file_name)



# 使用示例
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)