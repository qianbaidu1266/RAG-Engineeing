import os
from openai import OpenAI
import json
import dashscope
from math import sqrt, sin, cos  # 数学计算相关

client = OpenAI(
    api_key="sk-e4c8f84ef814473bbb396f5204d179d1",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

model_name = "qwen-plus"

system_prompt = """你是一个智能助手，需要根据问题类型选择合适工具获取信息。可用工具包括：
1. 天气查询工具（get_current_weather）- 查询城市天气
2. 数学计算工具（calculate_math_expression）- 执行数学运算
3. 单位换算工具（unit_converter）- 转换单位
4. 数值比较工具（compare_numbers）- 比较两个数值的大小
5. 版本比较工具（compare_versions）- 比较两个版本号的大小

请按照以下步骤工作：
1. 仔细分析用户问题类型（数值比较还是版本比较）
2. 数值比较示例："9.11和9.8哪个大"
3. 版本比较示例："版本号9.11和9.8哪个新"
4. 严格按参数要求调用工具
5. 最终给出清晰易懂的自然语言回答
"""


# ================== 工具函数定义 ==================
def get_current_weather(location: str, unit: str = 'celsius'):
    """模拟天气查询工具（实际应用中需接入真实API）"""
    weather_data = {
        "北京": {"temperature": 25, "unit": unit, "conditions": "晴朗"},
        "上海": {"temperature": 18, "unit": unit, "conditions": "多云"},
        "伦敦": {"temperature": 12, "unit": unit, "conditions": "小雨"}
    }
    return weather_data.get(location.lower(), "未找到该城市天气信息")


def calculate_math_expression(expression: str):
    """数学计算工具（注意：实际生产环境需做输入安全检查）"""
    try:
        return eval(expression)
    except:
        return "无法计算该表达式"


def unit_converter(value: float, from_unit: str, to_unit: str):
    """单位换算工具（支持长度、重量）"""
    conversion_rates = {
        "length": {"m": 1, "km": 1000, "cm": 0.01, "inch": 0.0254},
        "weight": {"kg": 1, "g": 0.001, "lb": 0.453592}
    }

    for category in conversion_rates:
        if from_unit in conversion_rates[category] and to_unit in conversion_rates[category]:
            return value * conversion_rates[category][from_unit] / conversion_rates[category][to_unit]
    return "单位转换不支持该类型"


# 在工具函数定义部分添加以下两个函数
def compare_numbers(number1: float, number2: float):
    """比较两个数值的大小"""
    try:
        num1 = float(number1)
        num2 = float(number2)
        return "大于" if num1 > num2 else "小于或等于"
    except ValueError:
        return "输入的不是有效数字"


def compare_versions(version1: str, version2: str):
    """比较两个版本号的大小（按语义化版本规范）"""

    def parse_version(v):
        parts = []
        for part in v.split('.'):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(part)
        return parts

    v1 = parse_version(version1)
    v2 = parse_version(version2)

    for p1, p2 in zip(v1, v2):
        if isinstance(p1, int) and isinstance(p2, int):
            if p1 != p2:
                return "新版本" if p1 > p2 else "旧版本"
        else:
            # 处理包含非数字部分的情况
            str_compare = str(p1) > str(p2)
            return "新版本" if str_compare else "旧版本"

    # 处理版本号长度不一致的情况
    return "新版本" if len(v1) > len(v2) else "旧版本" if len(v1) < len(v2) else "相同版本"



# ================== 工具声明 ==================
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "获取指定城市的当前天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市名称"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"], "description": "温度单位"}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_math_expression",
            "description": "计算数学表达式结果，支持基本运算和三角函数",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式，例如：sqrt(3^2 + 4^2)"}
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "unit_converter",
            "description": "执行单位换算（支持长度、重量）",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "number", "description": "需要转换的数值"},
                    "from_unit": {"type": "string", "enum": ["m", "km", "cm", "inch", "kg", "g", "lb"]},
                    "to_unit": {"type": "string", "enum": ["m", "km", "cm", "inch", "kg", "g", "lb"]}
                },
                "required": ["value", "from_unit", "to_unit"]
            }
        }
    },

{
        "type": "function",
        "function": {
            "name": "compare_numbers",
            "description": "比较两个数值的大小关系",
            "parameters": {
                "type": "object",
                "properties": {
                    "number1": {"type": "number", "description": "第一个数值"},
                    "number2": {"type": "number", "description": "第二个数值"}
                },
                "required": ["number1", "number2"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_versions",
            "description": "比较两个版本号的大小（按语义化版本规范）",
            "parameters": {
                "type": "object",
                "properties": {
                    "version1": {"type": "string", "description": "第一个版本号，例如：9.11"},
                    "version2": {"type": "string", "description": "第二个版本号，例如：9.8"}
                },
                "required": ["version1", "version2"]
            }
        }
    }
]


# ================== 工具调用处理器 ==================
def handle_tool_call(tool_call):
    func_name = tool_call.get('function').get('name')
    args = json.loads(tool_call.get('function').get('arguments'))

    if func_name == "get_current_weather":
        return get_current_weather(**args)
    elif func_name == "calculate_math_expression":
        return calculate_math_expression(args["expression"])
    elif func_name == "unit_converter":
        return unit_converter(**args)
    elif func_name == "compare_numbers":
        return compare_numbers(args["number1"], args["number2"])
    elif func_name == "compare_versions":
        return compare_versions(args["version1"], args["version2"])
    else:
        return "未知工具调用"


# ================== 对话流程 ==================
def run_conversation(user_input):

    messages = [
        {"role": "system", "content": system_prompt},  # 系统角色消息
        {"role": "user", "content": user_input}  # 用户消息
    ]

    # 第一次调用：获取工具调用请求
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )

    print("response:")
    print(response.model_dump_json())

    response_data = json.loads(response.model_dump_json())

    print("思考过程：")
    data = response_data['choices'][0].get('message', {})

    message = data.get('tool_calls',[])
    print("message:")
    print(message)


    # 处理所有工具调用
    tool_responses = []
    if isinstance(message, list):  # 确保 message 是列表
        for tool_call in message:
            # print("tool_call:")
            # print(tool_call)  # 打印工具调用的整个字典
            # print("type of tool_call:", type(tool_call))  # 打印类型，确保是字典
            # print("function key exists:", 'function' in tool_call)  # 确保字典中有 'function' 键
            # print("function structure:", tool_call.get('function').get('name'))  # 打印 'function' 部分
            result = handle_tool_call(tool_call)
            tool_responses.append({
                "tool_call_id": tool_call['id'],
                "role": "tool",
                "name": tool_call.get('function').get('name'),
                "content": str(result)
            })
    else:
        # 处理没有工具调用的情况
        print("No tool calls found in message.")

    #只有在工具调用不为空时，才记录工具调用响应
    if tool_responses:
        # 添加工具响应到消息历史
        messages.append({"role": "assistant", "content": None, "tool_calls": message})
        messages.extend(tool_responses)

    # 第二次调用：生成最终回答
    second_response = client.chat.completions.create(
        model= model_name,
        messages=messages,
        tools=tools
    )
    return second_response.choices[0].message.content


# ================== 测试用例 ==================
if __name__ == "__main__":
    print("欢迎使用智能助手！请输入您的问题（输入'exit'或'quit'退出）")
    while True:
        user_input = input("\n您的问题：").strip()

        if user_input.lower() in ['exit', 'quit']:
            print("感谢使用，再见！")
            break
        if not user_input:
            print("输入不能为空，请重新输入")
            continue

        try:
            print("\n处理中...")
            response = run_conversation(user_input)
            print("\n助手回答：")
            print(response)
            print("=" * 50)
        except Exception as e:
            print(f"\n处理出错：{str(e)}")
            print("=" * 50)

    # test_cases = [
    #     "北京现在的天气怎么样？",
    #     "计算一下3的平方加上4的平方等于多少",
    #     "把10英寸转换成厘米",
    #     "先告诉我伦敦的天气（华氏度），然后计算sin(30度)"
    # ]
    #
    # for query in test_cases:
    #     print(f"\n用户问题：{query}")
    #     print("回答：", run_conversation(query))
    #     print("=" * 50)