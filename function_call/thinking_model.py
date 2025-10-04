from openai import OpenAI
import os

# 初始化OpenAI客户端
client = OpenAI(
    # 如果没有配置环境变量，请用阿里云百炼API Key替换：api_key="sk-xxx"
    api_key = "sk-e4c8f84ef814473bbb396f5204d179d1",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

reasoning_content = ""  # 定义完整思考过程
answer_content = ""     # 定义完整回复

messages = []
conversation_idx = 1
while True:
    is_answering = False   # 判断是否结束思考过程并开始回复
    print("="*20+f"第{conversation_idx}轮对话"+"="*20)
    conversation_idx += 1
    user_msg = {"role": "user", "content": input("请输入你的消息：")}
    messages.append(user_msg)
    # 创建聊天完成请求
    completion = client.chat.completions.create(
        # 您可以按需更换为其它深度思考模型
        model="qwen-plus-2025-04-28",
        messages=messages,
        # enable_thinking 参数开启思考过程，QwQ 与 DeepSeek-R1 模型总会进行思考，不支持该参数
        extra_body={"enable_thinking": True},
        stream=True,
        # stream_options={
        #     "include_usage": True
        # }
    )
    print("\n" + "=" * 20 + "思考过程" + "=" * 20 + "\n")
    for chunk in completion:
        # 如果chunk.choices为空，则打印usage
        if not chunk.choices:
            print("\nUsage:")
            print(chunk.usage)
        else:
            delta = chunk.choices[0].delta
            # 打印思考过程
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content != None:
                print(delta.reasoning_content, end='', flush=True)
                reasoning_content += delta.reasoning_content
            else:
                # 开始回复
                if delta.content != "" and is_answering is False:
                    print("\n" + "=" * 20 + "完整回复" + "=" * 20 + "\n")
                    is_answering = True
                # 打印回复过程
                print(delta.content, end='', flush=True)
                answer_content += delta.content
    # 将模型回复的content添加到上下文中
    messages.append({"role": "assistant", "content": answer_content})
    print("\n")