

# 📘 Step 1: 加载 PDF 转图像
from pdf2image import convert_from_path

pdf_path = "climate_youth_magazine.pdf"  # 替换为你的 PDF 路径
images = convert_from_path(pdf_path)

# 选择某一页作为检索对象
query_image = images[5]  # 示例为第 6 页
text_query = "How much has the Earth's temperature increased since the 19th century?"



# 🔍 Step 2: 加载 ColPali 索引器（byaldi 提供封装）
from byaldi import RAGMultiModalModel

RAG = RAGMultiModalModel.from_pretrained("vidore/colpali")
# 索引构建（可批量执行）
RAG.index(images)  # 假设对整个 PDF 的图像建索引


# 🔍 Step 3: 使用文本查询检索相关图像页面
results = RAG.query(text_query, top_k=1)
image_index = results[0]['page_num'] - 1
retrieved_image = images[image_index]

# ✨ Step 4: 使用 Qwen2-VL 模型进行生成式回答
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
import torch

# 加载模型和处理器（可选更大版本如 7B）
model = Qwen2VLForConditionalGeneration.from_pretrained(
    "Qwen/Qwen2-VL-2B-Instruct",
    trust_remote_code=True,
    torch_dtype=torch.bfloat16
).cuda().eval()

processor = AutoProcessor.from_pretrained("Qwen/Qwen2-VL-2B-Instruct", trust_remote_code=True)

# 构造多模态输入消息
messages = [{
    "role": "user",
    "content": [
        {"type": "image", "image": retrieved_image},
        {"type": "text", "text": text_query},
    ],
}]

# 处理输入
text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
image_inputs, video_inputs = process_vision_info(messages)

inputs = processor(
    text=[text],
    images=image_inputs,
    videos=video_inputs,
    padding=True,
    return_tensors="pt"
).to("cuda")

# 生成回答
generated_ids = model.generate(**inputs, max_new_tokens=50)
output_ids_trimmed = [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)]
output_text = processor.batch_decode(output_ids_trimmed, skip_special_tokens=True)

# 🧾 输出最终答案
print("🔎 Answer:", output_text[0])

