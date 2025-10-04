import os
from pathlib import Path
from typing import Optional, Union, List, Dict, Any
from PIL import Image
import requests
from io import BytesIO
import base64
import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()  # 加载.env文件中的环境变量

# ------------------ Image Describer ------------------

class ImageDescriber:
    def __init__(
        self,
        model_name: str = "qwen2.5-vl-32b-instruct",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key: Optional[str] = None,
    ):
        self.model_name = model_name
        self.client = OpenAI(
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
            base_url=base_url
        )

    def _load_image(self, image_source: Union[str, Path, bytes]) -> Image.Image:
        try:
            if isinstance(image_source, (str, Path)):
                if str(image_source).startswith(('http://', 'https://')):
                    response = requests.get(str(image_source))
                    response.raise_for_status()
                    image = Image.open(BytesIO(response.content))
                else:
                    image = Image.open(image_source)
            elif isinstance(image_source, bytes):
                image = Image.open(BytesIO(image_source))
            else:
                raise ValueError("不支持的图片来源类型")
            if image.mode != "RGB":
                image = image.convert("RGB")
            return image
        except Exception as e:
            raise ValueError(f"加载图片失败: {str(e)}")

    def get_description(self, image_source: Union[str, Path, bytes]) -> str:
        image = self._load_image(image_source)
        buffered = BytesIO()
        image.save(buffered, format="JPEG", quality=85)
        img_str = base64.b64encode(buffered.getvalue()).decode()

        prompt = "你是一个专业的图像理解专家，擅长视觉语义分析、物体检测和文字识别。请生成一段简洁的图片描述，用于知识库的语义检索。描述应该包含图片的主要内容、场景、物体和文字（如果有）。"
        messages = [
            {"role": "system", "content": [{"type": "text", "text": "你是一个专业的图片描述助手。"}]},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}},
                {"type": "text", "text": prompt}
            ]}
        ]
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            return completion.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"生成图片描述失败: {str(e)}")


# ------------------ Image Formatter ------------------

class ImageFormatter:
    def __init__(self, format_type: str = "markdown"):
        self.format_type = format_type.lower()
        if self.format_type not in ["html", "markdown"]:
            raise ValueError("format_type must be either 'html' or 'markdown'")

    def format_image(self, image_path: str, description: str, metadata: Optional[dict] = None) -> str:
        if not image_path or not description:
            raise ValueError("image_path and description are required")
        if self.format_type == "html":
            return self._format_html(image_path, description, metadata)
        else:
            return self._format_markdown(image_path, description, metadata)

    def _format_html(self, image_path: str, description: str, metadata: Optional[dict] = None) -> str:
        metadata_text = ""
        if metadata:
            metadata_text = "<div class='metadata'>\n"
            for key, value in metadata.items():
                metadata_text += f"<p><strong>{key}:</strong> {value}</p>\n"
            metadata_text += "</div>"
        return f"""
<figure>
    <img src="{image_path}" alt="{description[:100]}..." style="max-width:100%;height:auto;">
    <figcaption>{description}</figcaption>
    {metadata_text}
</figure>
"""

    def _format_markdown(self, image_path: str, description: str, metadata: Optional[dict] = None) -> str:
        metadata_text = ""
        if metadata:
            metadata_text = "\n\n**元数据：**\n"
            for key, value in metadata.items():
                metadata_text += f"- {key}: {value}\n"
        return f"""
![{description[:100]}...]({image_path})
{description}{metadata_text}
"""


# ------------------ Vector Store ------------------

class ImageVectorStore:
    def __init__(self, persist_directory: str = "vector_db"):
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name="images",
            embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
        )

    def add_image(self, formatted_text: str, image_path: str, metadata: Optional[dict] = None):
        if not formatted_text or not image_path:
            raise ValueError("formatted_text and image_path are required")
        try:
            existing_ids = self.collection.get()["ids"]
            next_id = str(len(existing_ids) + 1)
            self.collection.add(
                documents=[formatted_text],
                metadatas=[{"image_path": image_path, **(metadata or {})}],
                ids=[next_id]
            )
        except Exception as e:
            raise RuntimeError(f"添加图片到向量数据库失败: {str(e)}")

    def search(self, query: str, n_results: int = 5) -> Dict[str, Any]:
        if not query:
            raise ValueError("query is required")
        try:
            return self.collection.query(
                query_texts=[query],
                n_results=min(n_results, 10)
            )
        except Exception as e:
            raise RuntimeError(f"搜索图片失败: {str(e)}")


# ------------------ RAG System ------------------

class ImageRAG:
    def __init__(
        self,
        image_describer: ImageDescriber,
        image_formatter: ImageFormatter,
        vector_store: ImageVectorStore,
        llm_client: OpenAI
    ):
        self.image_describer = image_describer
        self.image_formatter = image_formatter
        self.vector_store = vector_store
        self.llm_client = llm_client

    def process_image(self, image_path: str, metadata: Optional[dict] = None):
        try:
            description = self.image_describer.get_description(image_path)
            formatted_text = self.image_formatter.format_image(image_path, description, metadata)
            self.vector_store.add_image(formatted_text, image_path, metadata)
            return True
        except Exception as e:
            raise RuntimeError(f"处理图片失败: {str(e)}")

    def query(self, question: str, n_results: int = 5) -> Dict[str, Any]:
        if not question:
            raise ValueError("question is required")
        try:
            results = self.vector_store.search(question, n_results)
            context = "\n\n".join(results["documents"][0])
            messages = [
                {
                    "role": "system",
                    "content": "你是一位专业领域的AI知识助手，擅长整合文本、图片和表格数据来回答问题。请根据提供的图片描述和元数据，生成准确、全面的回答。在回答中，你可以直接引用图片描述中的内容，并在在回答中包含图片链接。"
                },
                {
                    "role": "user",
                    "content": f"问题：{question}\n\n相关图片信息：\n{context}"
                }
            ]
            completion = self.llm_client.chat.completions.create(
                model="qwen2.5-vl-32b-instruct",
                messages=messages,
                max_tokens=2000,
                temperature=0.7
            )
            return {
                "answer": completion.choices[0].message.content,
                "images": [
                    {
                        "rank": i + 1,
                        "formatted_text": doc,
                        "image_path": metadata["image_path"],
                        "similarity_score": results["distances"][0][i]
                    }
                    for i, (doc, metadata) in enumerate(zip(results["documents"][0], results["metadatas"][0]))
                ]
            }
        except Exception as e:
            raise RuntimeError(f"查询失败: {str(e)}")


# ------------------ Main Demo ------------------

if __name__ == "__main__":
    # 初始化各组件（使用阿里云百炼）
    describer = ImageDescriber(
        model_name="qwen2.5-vl-32b-instruct",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=os.getenv("DASHSCOPE_API_KEY")
    )

    formatter = ImageFormatter(format_type="markdown")
    vector_store = ImageVectorStore("vector_db")

    llm_client = OpenAI(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=os.getenv("DASHSCOPE_API_KEY")
    )

    rag = ImageRAG(describer, formatter, vector_store, llm_client)

    # 示例图片（请替换为你自己的本地图像路径）
    image_path = "./pictures/zhouyu.jpg"  # 确保此图片存在
    metadata = {"source": "user_upload", "date": "2024-03-20"}

    # 处理图像
    try:
        rag.process_image(image_path, metadata)
        print("✅ 图像处理完成")
    except Exception as e:
        print(f"❌ 图像处理失败: {str(e)}")

    # 问答检索
    try:
        results = rag.query("这张图片展示了什么？")
        print("\n🧠 回答：\n")
        print(results["answer"])
        print("\n📸 相关图片：")
        for img in results["images"]:
            print(f"\n排名 {img['rank']}:")
            print(img["formatted_text"])
            print(f"相似度: {img['similarity_score']}")
    except Exception as e:
        print(f"❌ 查询失败: {str(e)}")
