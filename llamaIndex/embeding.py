from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import Settings

# 指定本地模型路径
model_path = "G://AIGC//Dify//bge-large-zh-v1.5"

# 设置嵌入模型
Settings.embed_model = HuggingFaceEmbedding(model_name=model_path)

# 获取文本嵌入
embeddings = Settings.embed_model.get_text_embedding("Hello World!")
print(len(embeddings))  # 输出嵌入向量的维度
print(embeddings[:5])   # 输出前5个嵌入值


if __name__ == "__main__":
    # 获取文本嵌入
    embeddings = Settings.embed_model.get_text_embedding("Hello World!")
    print(len(embeddings))  # 输出嵌入向量的维度
    print(embeddings[:5])  # 输出前5个嵌入值