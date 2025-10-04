import os
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import asyncio
from sklearn.metrics.pairwise import cosine_similarity

# FastAPI 实例
app = FastAPI()

# 示例文档（用于检索）
documents = [
    "RAG 是一种结合检索和生成的技术",
    "RAG 在自然语言处理领域应用广泛",
    "机器学习和深度学习是现代 AI 技术的基础",
    "NLP 是人工智能的一个重要子领域"
]


# 模型输入的数据模型
class QADocs(BaseModel):
    query: str
    documents: List[str]
    top_n: int = 3  # 默认返回前3个结果


# BM25 简化实现
def simple_bm25(query, docs, top_n):
    N = len(docs)
    doc_freq = {}
    for doc in docs:
        words = set(doc.split())
        for word in words:
            doc_freq[word] = doc_freq.get(word, 0) + 1
    idf = {word: np.log((N - count + 0.5) / (count + 0.5) + 1.0) for word, count in doc_freq.items()}

    scores = []
    for doc in docs:
        score = 0
        doc_words = doc.split()
        query_words = query.split()
        for word in query_words:
            if word in doc_words:
                tf = doc_words.count(word)
                score += tf * idf.get(word, 0)
        scores.append(score)

    # 排序并返回 top_n
    sorted_doc_indices = np.argsort(scores)[::-1]
    return [{"document": docs[i], "score": scores[i]} for i in sorted_doc_indices[:top_n]]


# 简单的 Embedding 检索（通过余弦相似度计算）
def simple_embedding(query, docs, top_n):
    def query_vector_fn(text):
        return np.array([len(word) for word in text.split()])

    doc_vectors = [query_vector_fn(doc) for doc in docs]
    query_vector = query_vector_fn(query)
    scores = cosine_similarity([query_vector], doc_vectors).flatten()

    # 排序并返回 top_n
    sorted_doc_indices = np.argsort(scores)[::-1]
    return [{"document": docs[i], "score": scores[i]} for i in sorted_doc_indices[:top_n]]


# 并行执行 BM25 和 Embedding 检索
async def parallel_retrieval(query, docs, top_n):
    bm25_results = await asyncio.to_thread(simple_bm25, query, docs, top_n)
    embedding_results = await asyncio.to_thread(simple_embedding, query, docs, top_n)

    return bm25_results, embedding_results


# 合并 BM25 和 Embedding 检索的结果，并加权评分
def combine_scores(bm25_results, embedding_results, bm25_weight=0.5, embedding_weight=0.5):
    bm25_scores = {doc['document']: doc['score'] for doc in bm25_results}
    embedding_scores = {doc['document']: doc['score'] for doc in embedding_results}

    combined_scores = {}
    for doc in bm25_scores:
        # 将 BM25 和 Embedding 的得分加权合并
        bm25_score = bm25_scores.get(doc, 0)
        embedding_score = embedding_scores.get(doc, 0)
        combined_scores[doc] = bm25_weight * bm25_score + embedding_weight * embedding_score

    # 按照合并得分进行排序
    return sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)


# 重排序并返回 top_n
async def rerank_documents(query, docs, top_n=3, bm25_weight=0.5, embedding_weight=0.5):
    bm25_results, embedding_results = await parallel_retrieval(query, docs, top_n)  # 异步等待检索结果
    combined_results = combine_scores(bm25_results, embedding_results, bm25_weight, embedding_weight)
    # 返回 top_n
    return [{"document": doc, "score": score} for doc, score in combined_results[:top_n]]


# FastAPI 接口：接收查询，返回重排后的文档
@app.post('/v1/rerank')
async def handle_post_request(docs: QADocs):
    try:
        results = await rerank_documents(docs.query, docs.documents, top_n=docs.top_n)
        return {"results": results}
    except Exception as e:
        print(f"报错：\n{e}")
        raise HTTPException(status_code=500, detail="重排出错")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000)