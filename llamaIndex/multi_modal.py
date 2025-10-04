import os
import fitz  # PyMuPDF
import base64
from PIL import Image
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from llama_index import (
    SimpleDirectoryReader,
    VectorStoreIndex,
    StorageContext,
    ServiceContext
)
from llama_index.embeddings import HuggingFaceEmbedding
from llama_index.vector_stores import QdrantVectorStore
import qdrant_client

# 配置环境
os.environ["QDRANT_HOST"] = "localhost"  # 本地Qdrant服务
PDF_PATH = "your_document.pdf"

EMBEDDING_MODEL = "G://AIGC//Dify//bge-large-zh-v1.5"

# --- 1. 初始化Qwen-VL模型 ---
model_name = "qwen-vl-max-latest"
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    device_map="auto",
    trust_remote_code=True
).eval()


def qwen_vl_generate(prompt, image_path=None):
    """调用Qwen-VL生成回答"""
    if image_path:
        query = tokenizer.from_list_format([{
            'image': image_path,
            'text': prompt
        }])
    else:
        query = prompt

    response, _ = model.chat(tokenizer, query=query, history=None)
    return response


# --- 2. PDF解析（提取文本和图像）---
def extract_pdf_content(pdf_path):
    doc = fitz.open(pdf_path)
    content = {"text": [], "images": []}

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)

        # 提取文本
        text_blocks = page.get_text("blocks")
        for block in text_blocks:
            if block[6] == 0:  # 文本块
                content["text"].append({
                    "text": block[4],
                    "page": page_num
                })

        # 提取图像并保存临时文件
        image_list = page.get_images(full=True)
        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            img_bytes = base_image["image"]
            img = Image.open(BytesIO(img_bytes))
            img_path = f"temp_img_page{page_num}_{img_index}.png"
            img.save(img_path)
            content["images"].append({
                "path": img_path,
                "page": page_num
            })

    return content


# --- 3. 构建多模态索引 ---
def build_index(text_content):
    """构建纯文本索引（图像通过路径直接关联）"""
    # 初始化文本嵌入模型
    embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)

    # 创建Qdrant向量库
    client = qdrant_client.QdrantClient(os.getenv("QDRANT_HOST"))
    vector_store = QdrantVectorStore(client=client, collection_name="text_data")

    # 构建索引
    documents = [{"text": item["text"], "metadata": {"page": item["page"]}}
                 for item in text_content]
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=StorageContext.from_defaults(vector_store=vector_store),
        embed_model=embed_model
    )
    return index


# --- 4. 问答系统 ---
class MultimodalQA:
    def __init__(self, index, image_content):
        self.index = index
        self.image_content = image_content
        self.retriever = index.as_retriever(similarity_top_k=2)

    def query(self, question):
        # 文本检索
        text_results = self.retriever.retrieve(question)
        context = "\n".join([n.node.text for n in text_results])

        # 查找相关图像
        query_page = text_results[0].node.metadata["page"] if text_results else 0
        related_images = [img for img in self.image_content if img["page"] == query_page]

        # 调用Qwen-VL生成答案
        if related_images:
            image_path = related_images[0]["path"]
            full_prompt = f"上下文：{context}\n问题：{question}"
            answer = qwen_vl_generate(full_prompt, image_path)
        else:
            answer = qwen_vl_generate(f"上下文：{context}\n问题：{question}")

        return answer


# --- 主流程 ---
if __name__ == "__main__":
    # 1. 解析PDF
    print("解析PDF中...")
    content = extract_pdf_content(PDF_PATH)

    # 2. 构建索引
    print("构建文本索引...")
    index = build_index(content["text"])

    # 3. 初始化问答系统
    qa_system = MultimodalQA(index, content["images"])

    # 4. 示例查询
    questions = [
        "第二页的图片展示了什么内容？",
        "总结文档的主要观点",
        "第三页的图表说明了什么趋势？"
    ]

    for q in questions:
        print(f"\n问题：{q}")
        answer = qa_system.query(q)
        print(f"回答：{answer}\n{'=' * 50}")