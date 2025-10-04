from fastapi import FastAPI, Body, HTTPException
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI
import json
import pdfplumber
from openai import OpenAI
import json
import dashscope
from math import sqrt, sin, cos  # 数学计算相关
import os
from dotenv import load_dotenv
load_dotenv()  # 加载.env文件中的环境变量


app = FastAPI()

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

model_name = "qwen-plus"


# 方法二：使用 pdfplumber 库（更准确的文本提取，支持表格）
async def read_pdf_with_pdfplumber(file_name):
    """
    使用 pdfplumber 读取PDF文件内容
    安装：pip install pdfplumber
    """

    file_path = "G://AIGC//ChatWithFiles//"
    file = file_path + file_name
    try:
        text = ""
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text += page.extract_text()
        return text.strip()[0:5000]
    except FileNotFoundError:
        return f"错误：文件 {file} 不存在"
    except Exception as e:
        return f"发生错误：{str(e)}"


async def match_pdfs_with_llm(query: str) -> json:
    """第一次调用：大模型匹配PDF文件"""
    # 1. 读取目录文件
    files_info = await read_pdf_with_pdfplumber("现行制度体系.pdf")
    system_prompt = """
    请根据制度文档的目录信息，分析用户的问题应该查找哪些文档，如果用户的问题不属于目录中的分类，请直接返回无相关分类。
    目录信息："""+files_info + """
    请返回严格遵循以下JSON格式的结果，JSON包含以下字段：
    1. matched_files：一个列表，包含最匹配的PDF文件名。
    2. reasoning：一个字符串，包含你匹配文件的理由。
    案例1：
    用户提问：中国的支付体系是怎样的？
    返回：
    {
     "matched_files":["中国支付体系发展报告2016.pdf"],
     "reasoning":"用户的问题属于支付体系分类。"
    }
    案例2：
    用户提问：今天天气怎么样？
    返回：
    {
     "matched_files":[],
     "reasoning":"无相关分类。"
    }
    """
    # 2. 构造提示词
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": query}]

    try:
        # 1. 验证输入
        if not query.strip():
            raise ValueError("问题内容不能为空")

        # 3. 调用大模型
        response = await client.chat.completions.create(
            model=model_name,
            messages= messages,
            temperature=0.7
        )

        # 4. 解析并验证结果
        response_data =  json.loads(response.model_dump_json())
        print("response_data:")
        print(response_data)

        data = response_data['choices'][0].get('message', {}).get('content', {})
        print("data:")
        print(data)
        messages.append({"role": "assistant", "content": data})
        return data

    except json.JSONDecodeError:
        return {"status": "error", "message": "大模型返回格式解析失败"}
    except Exception as e:
        return {"status": "error", "message": f"大模型调用失败: {str(e)}"}


async def answer_with_llm(data: json, query: str) -> str:
    """第二次调用：大模型匹配PDF文件"""
    # 1. 读取目录文件
    files = data.get('matched_files', [])
    if not files:
        return "没有找到相关信息，AI无法回答"
    relate_info = ""
    #遍历files数组
    for file in files:
        relate_info = relate_info + file + ":"
        relate_info = relate_info + await read_pdf_with_pdfplumber(file)

    system_prompt = """
    请根据参考信息简洁专业地回答用户的问题：
    参考信息：""" + relate_info + """
    """
    # 2. 构造提示词
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": query}]

    try:
        # 1. 验证输入
        if not query.strip():
            raise ValueError("问题内容不能为空")

        # 3. 调用大模型
        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.7
        )

        # 4. 解析并验证结果
        response_data = json.loads(response.model_dump_json())
        print("response_data:")
        print(response_data)

        data = response_data['choices'][0].get('message', {}).get('content', {})
        print("data:")
        print(data)
        messages.append({"role": "assistant", "content": data})
        return data
    except Exception as e:
        return {"status": "error", "message": f"大模型调用失败: {str(e)}"}

@app.post("/chat")
async def chat_with_files(query: str = Body(..., embed=True)) -> str:
    data = await match_pdfs_with_llm(query)
    print("****")
    print(type(data))
    print(data)
    print("***")
    input_data = json.loads(data)
    return answer_with_llm(input_data, query)

# 使用示例
if __name__ == "__main__":

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

    #file_name = "现行制度体系.pdf"
    # 使用 pdfplumber
    #print("\n使用 pdfplumber 读取结果：")
    #print(read_pdf_with_pdfplumber(file_name)[:50000])

    # while True:
    #     user_input = input("\n您的问题：").strip()
    #     #match_pdfs_with_llm(user_input)
    #     print(chat_with_files(user_input))