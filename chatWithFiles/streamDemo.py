
from openai import OpenAI
import json
from fastapi import FastAPI, Request, HTTPException


app = FastAPI()

client = OpenAI(
    api_key="sk-e4c8f84ef814473bbb396f5204d179d1",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

model_name = "qwen-plus"


def chat_with_model(messages):
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.7,
            stream=True
        )

        answer = ""
        for chunk in response:
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            # 处理增量内容
            if hasattr(delta, "content"):
                content = delta.content
                answer += content
                yield content  # 逐步返回增量内容

            # 检查流式传输是否结束
            if choice.finish_reason == "stop":
                break

        # 将完整回答追加到消息历史
        messages.append({"role": "assistant", "content": answer})

    except Exception as e:
        # 返回结构化错误信息
        error_info = {"status": "error", "message": f"大模型调用失败: {str(e)}"}
        yield error_info  # 使用yield返回错误信息


# 使用示例
if __name__ == "__main__":
    messages = [
        {"role": "system", "content": "你是智能小助手，请回答用户的问题"},
        {"role": "user", "content": "今天天气怎么样"}
    ]

    for chunk in chat_with_model(messages):
        if isinstance(chunk, str):  # 正常情况：返回字符串增量内容
            print(f"收到新内容: {chunk}")
        else:  # 异常情况：返回错误信息
            print(f"错误: {chunk['message']}")