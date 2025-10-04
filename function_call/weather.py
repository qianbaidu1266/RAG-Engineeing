import openai
import os
from dotenv import load_dotenv
import requests

# 加载环境变量

# 配置 OpenAI API 和 DeepSeek API
api_key = "sk-e4c8f84ef814473bbb396f5204d179d1"
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

model_name = "deepseek-r1"

# 设置 DeepSeek 客户端
client = openai.OpenAI(api_key=api_key, base_url=base_url)

# 高德地图天气 API
weather_api_key = "b7917dc666e205b4df95915396bf22f9"
weather_base_url = "https://restapi.amap.com/v3/weather/weatherInfo"


class WeatherAgent:
    def __init__(self):
        self.client = client
        self.system_prompt = "你是一个智能助手，能够提供天气查询服务。请用户提供城市名，查询并返回当地的天气情况。"
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def get_weather_info(self, city_name):
        """查询天气信息（带错误处理）"""
        params = {
            'key': weather_api_key,
            'city': city_name,
            'extensions': 'base',
            'output': 'JSON'
        }

        try:
            response = requests.get(weather_base_url, params=params)
            response.raise_for_status()  # 自动触发HTTP错误

            weather_data = response.json()
            if weather_data.get('status') != '1':
                return f"请求失败：{weather_data.get('infocode', '未知错误')}"

            lives = weather_data.get('lives', [])
            if not lives:
                return "该城市无天气数据"

            live_data = lives[0]
            return (
                f"当前天气：{live_data['weather']}\n"
                f"温度：{live_data['temperature']}°C\n"
                f"湿度：{live_data['humidity']}%\n"
                f"更新时间：{live_data['reporttime']}"
            )

        except requests.exceptions.RequestException as e:
            return f"网络请求失败：{str(e)}"
        except KeyError as e:
            return f"数据解析错误：缺少字段 {str(e)}"

    def get_response(self, user_input):
        """改进后的响应逻辑"""
        self.messages.append({"role": "user", "content": user_input})

        # 通过AI识别城市名（更精准）
        prompt = f"""
        用户问：{user_input}
        请严格按以下格式回答，只需返回城市名,提取的城市要符合查询标准，尽量是标准城市命名：
        {{
            "city": "提取到的城市名"
        }}
        如果无法识别则返回：{{"city": null}}
        """

        # 调用模型提取城市
        extraction_response = self.client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=50
        )

        # 解析城市名
        try:
            city_info = eval(extraction_response.choices[0].message.content)
            city_name = city_info.get('city')
        except:
            city_name = None

        if city_name:
            weather_info = self.get_weather_info(city_name)
            return weather_info
        else:
            # 普通对话
            response = self.client.chat.completions.create(
                model=model_name,
                messages=self.messages,
                temperature=0.7,
                stream=False,
                max_tokens=1000
            )
            return response.choices[0].message.content


# 测试
if __name__ == "__main__":
    agent = WeatherAgent()

    test_cases = [
        "北京天气怎么样？",
        "上海市浦东新区今天会下雨吗",
        "帮我查一个不存在的城市的天气",  # 测试错误处理
        "讲个笑话"
    ]

    for query in test_cases:
        print(f"用户：{query}")
        print(f"助手：{agent.get_response(query)}\n")