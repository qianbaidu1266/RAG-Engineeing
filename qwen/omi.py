
import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()  # 加载.env文件中的环境变量

client = OpenAI(
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)


def text():
    completion = client.chat.completions.create(
        model="qwen-omni-turbo",
        messages=[{"role": "user", "content": "今天天气怎么样？"}],
        # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
        modalities=["text", "audio"],
        audio={"voice": "Cherry", "format": "wav"},
        # stream 必须设置为 True，否则会报错
        stream=True,
        stream_options={"include_usage": True},
    )

    for chunk in completion:
        if chunk.choices:
            print(chunk.choices[0].delta)
        else:
            print(chunk.usage)


def picture():
    completion = client.chat.completions.create(
        model="qwen-omni-turbo",
        messages=[
            {
                "role": "system",
                "content": [{"type": "text", "text": "你是一个智能助手，请简洁专业地回答用户的问题。"}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241022/emyrja/dog_and_girl.jpeg"
                        },
                    },
                    {"type": "text", "text": "图中描绘的是什么景象？"},
                ],
            },
        ],
        # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
        modalities=["text", "audio"],
        audio={"voice": "Chelsie", "format": "wav"},
        # stream 必须设置为 True，否则会报错
        stream=True,
        stream_options={
            "include_usage": True
        }
    )
    for chunk in completion:
        if chunk.choices:
            print(chunk.choices[0].delta)
        else:
            print(chunk.usage)

# ================== 测试用例 ==================
if __name__ == "__main__":
    picture()