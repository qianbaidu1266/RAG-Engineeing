import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()  # 加载.env文件中的环境变量

# 初始化 OpenAI 客户端，使用阿里云魔搭平台的兼容模式
client = OpenAI(
    # 从环境变量中获取 DASHSCOPE_API_KEY，若未配置环境变量，可直接填写 API Key
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

model_name = "deepseek-r1"

# Define system prompts for different tasks
sys_prompt = """你是一个聪明的客服。您将能够根据用户的问题将不同的任务分配给不同的人。您有以下业务线：
1.用户注册。如果用户想要执行这样的操作，您应该发送一个带有"registered workers"的特殊令牌。并告诉用户您正在调用它。
2.用户数据查询。如果用户想要执行这样的操作，您应该发送一个带有"query workers"的特殊令牌。并告诉用户您正在调用它。
3.删除用户数据。如果用户想执行这种类型的操作，您应该发送一个带有"delete workers"的特殊令牌。并告诉用户您正在调用它。
"""

registered_prompt = """
您的任务是根据用户信息存储数据。您需要从用户那里获得以下信息：
1.用户名、性别、年龄
2.用户设置的密码
3.用户的电子邮件地址
如果用户没有提供此信息，您需要提示用户提供。如果用户提供了此信息，则需要将此信息存储在数据库中，并告诉用户注册成功。
"""

query_prompt = """
您的任务是查询用户信息。您需要从用户那里获得以下信息：
1.用户ID
2.用户设置的密码
如果用户没有提供此信息，则需要提示用户提供。如果用户提供了此信息，那么需要查询数据库。如果用户ID和密码匹配，则需要返回用户的信息。
"""

delete_prompt = """
您的任务是删除用户信息。您需要从用户那里获得以下信息：
1.用户ID
2.用户设置的密码
3.用户的电子邮件地址
如果用户没有提供此信息，则需要提示用户提供该信息。
"""


class SmartAssistant:
    def __init__(self):
        self.client = client

        # Define system prompts for different tasks
        self.system_prompt = sys_prompt
        self.registered_prompt = registered_prompt
        self.query_prompt = query_prompt
        self.delete_prompt = delete_prompt

        # Using a dictionary to store different sets of messages
        self.messages = {
            "system": [{"role": "system", "content": self.system_prompt}],
            "registered": [{"role": "system", "content": self.registered_prompt}],
            "query": [{"role": "system", "content": self.query_prompt}],
            "delete": [{"role": "system", "content": self.delete_prompt}]
        }

        # Current assignment for handling messages
        self.current_assignment = "system"

    def get_response(self, user_input):
        # Append user input to the current assignment's messages
        self.messages[self.current_assignment].append({"role": "user", "content": user_input})

        # Get response from the AI model
        completion = self.client.chat.completions.create(
            model=model_name,  # 此处以 qwen-plus 为例，可按需更换模型名称
            messages=self.messages[self.current_assignment],
            temperature=0.9,
            max_tokens=2000
        )

        # Extract AI response
        ai_response = completion.choices[0].message.content

        # Check for special tokens and switch assignment if necessary
        if "registered workers" in ai_response:
            self.current_assignment = "registered"
            self.messages[self.current_assignment].append({"role": "user", "content": user_input})
        elif "query workers" in ai_response:
            self.current_assignment = "query"
            self.messages[self.current_assignment].append({"role": "user", "content": user_input})
        elif "delete workers" in ai_response:
            self.current_assignment = "delete"
            self.messages[self.current_assignment].append({"role": "user", "content": user_input})

        return ai_response


# Example usage
if __name__ == "__main__":
    assistant = SmartAssistant()
    while True:
        user_input = input("You: ")
        # if user_input.lower() in ["exit", "quit"]:
        #     break
        response = assistant.get_response(user_input)
        print(f"Assistant: {response}")