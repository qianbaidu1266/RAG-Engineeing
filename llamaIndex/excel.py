import os
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings, load_index_from_storage, StorageContext,Document
from openai import AsyncOpenAI
import openai
import asyncio
import shutil
from openpyxl import load_workbook


# 基于LlamaIndex 构建的PDF问答系统

# 配置初始化
app = FastAPI(title="PDF QA System")

client = openai.AsyncOpenAI(
    api_key="sk-e4c8f84ef814473bbb396f5204d179d1",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# 模型配置
class ModelConfig:
    DATA_DIR = "G://AIGC//ChatWithFiles//xlsx//"  # 需要确保此目录存在
    EMBEDDING_MODEL = "G://AIGC//Dify//bge-large-zh-v1.5"
    model_name = "qwen-plus"  # 可替换为其他支持chat.completions接口的模型
    INDEX_SAVE_PATH = "./excel_store"  # 索引存储路径


# 请求模型
class QueryRequest(BaseModel):
    question: str
    chat_history: Optional[List[dict]] = []


# 自定义读取Excel文件并封装为文档对象
def load_xlsx_files_from_directory(directory_path):
    documents = []
    for filename in os.listdir(directory_path):
        if filename.endswith(".xlsx"):
            file_path = os.path.join(directory_path, filename)
            try:
                # 读取Excel文件
                wb = load_workbook(file_path)
                for sheet in wb.sheetnames:
                    sheet_data = wb[sheet]
                    text_content = ""
                    for row in sheet_data.iter_rows(values_only=True):
                        # 将每一行的单元格内容拼接成文本
                        text_content += " ".join(map(str, row)) + "\n"

                    # 使用llama_index提供的Document对象封装文档
                    doc = Document(text=text_content)  # 只传递text内容作为参数
                    documents.append(doc)
            except Exception as e:
                print(f"读取文件 {filename} 时出错: {e}")
    return documents


# 初始化系统
# 初始化 RAG 系统
def initialize_rag_system():
    # 配置嵌入模型
    Settings.embed_model = HuggingFaceEmbedding(model_name=ModelConfig.EMBEDDING_MODEL)
    Settings.llm = None  # 禁用 LLM，避免 OpenAI 相关错误
    os.makedirs(ModelConfig.INDEX_SAVE_PATH, exist_ok=True)

    # 如果索引已存在，直接加载
    if os.path.exists(ModelConfig.INDEX_SAVE_PATH) and os.listdir(ModelConfig.INDEX_SAVE_PATH):
        print("加载已有索引...")
        storage_context = StorageContext.from_defaults(persist_dir=ModelConfig.INDEX_SAVE_PATH)
        return load_index_from_storage(storage_context)

    # 否则，重新加载 .xlsx 文件并创建索引
    print("索引文件不存在，重新创建索引...")
    if not os.path.exists(ModelConfig.DATA_DIR):
        os.makedirs(ModelConfig.DATA_DIR)

    # 使用自定义加载器读取 .xlsx 文件并封装为文档对象
    documents = load_xlsx_files_from_directory(ModelConfig.DATA_DIR)

    # 创建索引
    index = VectorStoreIndex.from_documents(documents, show_progress=True)
    # 保存索引到磁盘
    index.storage_context.persist(persist_dir=ModelConfig.INDEX_SAVE_PATH)
    print("索引已保存到磁盘。")
    return index


# 初始化索引
index = initialize_rag_system()

# 生成问题+相关文档的提示词
system_prompt = f"""
   你是一个制度问答智能助手，请根据制度文档参考信息简洁专业地回答用户问题：
   回答策略：
   1.如果制度文档参考信息为空，提示用户没有找到相关的制度文档，引导用户问具体的制度方面的问题。
   2.透明化操作：在处理用户请求过程中，如果参考了制度文档的信息，简要告知用户制度文档的名称，增加信息来源的透明度和可信度。
   3.确认与跟进：解答完毕后，确认用户是否满意解答，并主动询问是否有其他可以帮助的地方，如：“请问还有其他问题需要我的帮助吗？”
   """

messages = [
    {"role": "system", "content": system_prompt},
]


# 核心处理函数
async def generate_answer(query: str, context: str) -> str:
    # **合并参考信息与用户问题**
    combined_query = f"用户问题：{query}\n参考文档信息：\n{context}"
    # 添加当前用户的提问
    messages.append({"role": "user", "content": combined_query})

    response = await client.chat.completions.create(
        model=ModelConfig.model_name,
        messages=messages,
        temperature=0.7
    )
    answer = response.choices[0].message.content
    messages.append({"role": "assistant", "content": answer})
    return answer


# API接口
@app.post("/query")
async def query_endpoint(request: QueryRequest):
    try:
        # 检索相关上下文
        query_engine = index.as_query_engine()
        retrieved_context = query_engine.query(request.question)

        # 生成最终回答
        final_answer = await generate_answer(
            query=request.question,
            context=str(retrieved_context)
        )
        print(f"""回答：{final_answer}""")
        return {"answer": final_answer}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 文件上传接口
@app.post("/upload")
async def upload_file(file: UploadFile):
    try:
        file_path = f"data/{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 重新加载索引
        global index
        index = initialize_rag_system()
        return {"status": "success", "filename": file.filename}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
