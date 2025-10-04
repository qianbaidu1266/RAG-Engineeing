import os
import torch
import openai
from openai import OpenAI
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, load_index_from_storage

#from llama_index.llms import OpenAI
#from llama_index.chat_engine import CondenseQuestionChatEngine
from llama_index.core.query_engine import RetrieverQueryEngine

# 配置路径
INDEX_SAVE_PATH = "./faiss_index"
DOCS_PATH = "G://AIGC//ChatWithFiles//"
EMBEDDING_MODEL_PATH = "G://AIGC//Dify//bge-large-zh-v1.5"  # 本地 Sentence-Transformer 模型路径
RE_RANK_MODEL_PATH = "G:/IGC/Dify/rerank/bge-reranker-large-main" # 本地重排序模型路径


# 加载 embedding 模型
def load_embedding_model():
    model = SentenceTransformer(EMBEDDING_MODEL_PATH)
    return model


# 加载重排序模型
def load_re_ranking_model():
    tokenizer = AutoTokenizer.from_pretrained(RE_RANK_MODEL_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(RE_RANK_MODEL_PATH)
    return tokenizer, model


# 配置 FastAPI
app = FastAPI()


# Pydantic 模型，用于请求体解析
class QueryRequest(BaseModel):
    query: str


# 加载本地索引
def get_index():
    if os.path.exists(INDEX_SAVE_PATH) and os.listdir(INDEX_SAVE_PATH):
        print("加载已有索引...")
        storage_context = StorageContext.from_defaults(persist_dir=INDEX_SAVE_PATH)
        return load_index_from_storage(storage_context)

    print("构建新索引...")
    documents = SimpleDirectoryReader(DOCS_PATH).load_data()
    #index = GPTVectorStoreIndex.from_documents(documents)
    index = VectorStoreIndex.from_documents(documents)
    index.storage_context.persist(persist_dir=INDEX_SAVE_PATH)
    return index


# 初始化检索器、LLM 和对话引擎
index = get_index()
retriever = index.as_retriever(similarity_top_k=5)
client = openai.AsyncOpenAI(
    api_key="sk-e4c8f84ef814473bbb396f5204d179d1",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

client = OpenAI(
    model="gpt-4",
    api_key="sk-e4c8f84ef814473bbb396f5204d179d1"
)
chat_engine = RetrieverQueryEngine.from_defaults(llm=client, retriever=retriever)

# 加载本地模型
embedding_model = load_embedding_model()
re_rank_tokenizer, re_rank_model = load_re_ranking_model()


# 模拟重排序过程
def rerank_results(results, query):
    # 使用重排序模型对检索结果进行评分
    inputs = re_rank_tokenizer([query] * len(results), results, return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        logits = re_rank_model(**inputs).logits
    scores = logits.squeeze().tolist()

    # 显示相关性得分
    sorted_results_with_scores = [(score, result) for score, result in sorted(zip(scores, results), reverse=True)]

    return sorted_results_with_scores


# 处理查询并返回响应
@app.post("/query")
async def query(request: QueryRequest):
    query = request.query

    # 使用检索器获取初步结果
    initial_results = retriever.retrieve(query)

    # 获取重排序结果及其得分
    reranked_results_with_scores = rerank_results(initial_results, query)

    # 生成优化后的回答
    response = chat_engine.chat(query)

    # 返回优化后的回答和排序后的检索结果
    return {
        "response": response,
        "reranked_results_with_scores": reranked_results_with_scores
    }


# 交互示例（仅用于调试）
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8085)