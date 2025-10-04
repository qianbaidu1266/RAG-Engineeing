import re
import time
from collections import deque

# 全局配置
DEBUG_MODE = True
USER_PERMISSIONS = ['weather', 'calculator', 'translator']


class ToolExecutionError(Exception):
    """自定义工具执行异常"""
    pass


class BaseTool:
    """工具基类"""

    def execute(self, context):
        raise NotImplementedError


class WeatherTool(BaseTool):
    def execute(self, context):
        location = extract_location(context['original_query'])
        if not location:
            raise ToolExecutionError("未识别到有效地理位置")

        # 模拟API调用
        weather_data = get_weather_api(location)
        return f"{location}的天气：{weather_data}"


class CalculatorTool(BaseTool):
    def execute(self, context):
        expression = extract_math_expression(context['original_query'])
        if not expression:
            raise ToolExecutionError("未识别到有效数学表达式")

        # 模拟计算
        try:
            result = eval(expression)
            return f"{expression} = {result}"
        except:
            raise ToolExecutionError("无法执行计算")


class TranslatorTool(BaseTool):
    def execute(self, context):
        # 优先使用上游结果
        text = context.get('weather_result', context.get('calculator_result', ""))
        if not text:
            text = extract_translation_text(context['original_query'])

        # 模拟翻译
        translated = translate_api(text, target='en')
        return f"翻译结果：{translated}"


class ToolManager:
    def __init__(self):
        self.tools = {
            'weather': WeatherTool(),
            'calculator': CalculatorTool(),
            'translator': TranslatorTool()
        }
        self.dependency_map = {
            'translator': ['weather', 'calculator']
        }

    def resolve_dependencies(self, required_tools):
        """使用Kahn算法进行拓扑排序"""
        in_degree = {tool: 0 for tool in required_tools}
        graph = {tool: [] for tool in required_tools}

        # 构建依赖图
        for tool in required_tools:
            for dep in self.dependency_map.get(tool, []):
                if dep in required_tools:
                    graph[dep].append(tool)
                    in_degree[tool] += 1

        # 初始化队列
        queue = deque([t for t in in_degree if in_degree[t] == 0])
        ordered = []

        while queue:
            node = queue.popleft()
            ordered.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != len(required_tools):
            raise ToolExecutionError("检测到循环依赖")

        return ordered


class IntentClassifier:
    def __init__(self):
        self.tool_patterns = {
            'weather': [
                r'天气|气温|温度',
                r'.*?([北南东西]京|上海|广州|深圳)的?天气'
            ],
            'calculator': [
                r'计算|等于|多少|加减|乘除',
                r'\d+[\+\-\*/]\d+'
            ],
            'translator': [
                r'翻译成英文|译为中文',
                r'用(英语|日语)怎么说'
            ]
        }

    def detect_tools(self, query):
        required_tools = set()
        for tool, patterns in self.tool_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    required_tools.add(tool)
                    break
        return list(required_tools)


def process_query(query):
    # 1. 意图识别
    classifier = IntentClassifier()
    required_tools = classifier.detect_tools(query)

    # 2. 基础对话处理
    if not required_tools:
        response = handle_basic_conversation(query)
        if response:
            return response
        return "我暂时无法回答这个问题，请尝试更明确的提问方式"

    # 3. 依赖解析
    tool_manager = ToolManager()
    try:
        execution_order = tool_manager.resolve_dependencies(required_tools)
    except ToolExecutionError as e:
        return f"系统错误：{str(e)}"

    # 4. 执行流水线
    context = {
        'original_query': query,
        'user_id': 'demo_user',
        'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
    }
    results = []

    try:
        for tool_name in execution_order:
            # 权限验证
            if not check_permission(tool_name):
                raise PermissionError(f"无权限使用 {tool_name} 工具")

            tool = tool_manager.tools[tool_name]
            result = tool.execute(context)

            # 记录结果
            context[f'{tool_name}_result'] = result
            results.append(result)

            # 模拟渐进式反馈
            if len(execution_order) > 1:
                print(f"[系统通知] {tool_name} 处理完成")

    except Exception as e:
        return handle_error(e, tool_name, context)

    # 5. 结果整合
    return integrate_results(results, context)


def check_permission(tool_name):
    return tool_name in USER_PERMISSIONS


def handle_error(error, tool_name=None, context=None):
    error_info = {
        "error_type": type(error).__name__,
        "tool": tool_name,
        "message": str(error),
        "context": context if DEBUG_MODE else None
    }
    print(f"错误日志：{error_info}")

    user_message = "抱歉，处理请求时遇到问题"
    if isinstance(error, PermissionError):
        user_message = "您没有权限使用此功能"
    elif isinstance(error, ToolExecutionError):
        user_message = f"处理失败：{str(error)}"

    return user_message + "（技术详情请查看日志）" if DEBUG_MODE else user_message


def integrate_results(results, context):
    if len(results) == 1:
        return results[0]

    response = ["处理完成，以下是分步结果："]
    for idx, result in enumerate(results, 1):
        response.append(f"{idx}. {result}")

    if DEBUG_MODE:
        response.append("\n[调试信息]")
        response.append(f"上下文：{context}")

    return "\n".join(response)


def handle_basic_conversation(query):
    conversation_db = {
        r'你好|hello': '你好！有什么可以帮您？',
        r'谢谢|感谢': '不客气，很高兴能帮助您！',
        r'再见|bye': '再见！祝您有美好的一天！',
        r'帮助|help': '我可以帮您查询天气、进行计算和翻译内容，请随时提问'
    }
    for pattern, response in conversation_db.items():
        if re.fullmatch(pattern, query, re.IGNORECASE):
            return response
    return None


# 模拟辅助函数
def extract_location(query):
    match = re.search(r'([北南东西]京|上海|广州|深圳)', query)
    return match.group(1) if match else "北京"


def get_weather_api(location):
    weather_db = {
        "北京": "晴 25℃",
        "上海": "多云 28℃",
        "广州": "阵雨 30℃",
        "深圳": "晴 32℃"
    }
    return weather_db.get(location, "未知地区")


def extract_math_expression(query):
    match = re.search(r'(\d+[\+\-\*/]\d+)', query)
    return match.group(1) if match else "3+5 * 2"


def extract_translation_text(query):
    match = re.search(r'翻译"(.*?)"', query)
    return match.group(1) if match else "默认文本"


def translate_api(text, target='en'):
    translations = {
        "北京的天气：晴 25℃": "Beijing weather: Sunny 25℃",
        "3+5 * 2 = 13": "3+5 * 2 = 13",
        "默认文本": "default text"
    }
    return translations.get(text, "translation unavailable")


# 测试用例
test_queries = [
    "你好",
    "北京今天的天气怎么样？",
    "请计算(15+7)*3的结果",
    "把北京的天气翻译成英文",
    "先计算1024除以16再翻译结果",
    "查看上海的天气和深圳的天气",
    "如何做蛋炒饭？"
]

if __name__ == "__main__":
    for query in test_queries:
        print(f"\n用户提问：{query}")
        print("系统回复：")
        print(process_query(query))
        print("-" * 50)