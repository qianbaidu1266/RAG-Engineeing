from openai import OpenAI


def get_threat_intelligence(product_name, version):
    return f'应用{product_name} , 版本为{version} 目前暂无漏洞。'


def send_messages_without_tools(messages):
    response = client.chat.completions.create(
        model="deepseek-ai/DeepSeek-V3",
        messages=messages,
        tools=tools
    )
    return response.choices[0].message


def send_messages(messages):
    response = client.chat.completions.create(
        # model="Qwen/Qwen2.5-32B-Instruct",
        model="deepseek-ai/DeepSeek-V3",
        messages=messages,
        tools=tools
    )
    return response.choices[0].message
# api_key="sk-219b3417008c4949949f2ad4dac045a2",
#     base_url="https://api.deepseek.com",


client = OpenAI(
    api_key="sk-ueskkqivdokojdqnwmrozbfuozpfxottlzsearghgwsqjomc",
    base_url="https://api.siliconflow.cn/v1",
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather of an location, the user should supply a location first",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    }
                },
                "required": ["location"]
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_threat_intelligence",
            "description": "The `get_threat_intelligence` function retrieves threat intelligence data related to a specific product. It takes a single string parameter, which represents the product name. The function queries various threat intelligence sources to gather security-related information, such as known vulnerabilities, indicators of compromise (IoCs), malicious activities, and potential threats associated with the given product. This information helps in risk assessment, security monitoring, and proactive threat mitigation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "The name of the product for which threat intelligence data is being retrieved. This can be a software application, hardware device, or service. The function uses this name to query threat intelligence sources and collect relevant security information, including vulnerabilities, threats, and indicators of compromise (IoCs).",
                    },
                    "version": {
                        "type": "string",
                        "description": "The version of the product."
                    }
                },
                "required": ["product_name", "version"]
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_project",
            "description": "The `get_project` function retrieves project information, you can find git url from this function.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "项目id",
                    }
                },
                "required": ["project_id"]
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_schema_info",
            "description": "The `get_schema_info` function retrieves project id and other about schema info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "schema_id": {
                        "type": "string",
                        "description": "The name of the schema id  for which get schema info is being retrieved",
                    }
                },
                "required": ["schema_id"]
            },
        }
    }
]

# messages = [{"role": "user", "content": "版本是1.1.0的jetty的威胁情报情况是什么?"}]
messages = [{"role": "user", "content": "帮我查一下schema id是50的git url地址是什么？再帮我看下北京天气怎么样？"}]
# messages = [{"role": "user", "content": "解读一下红楼梦"}]
# messages = [{"role": "user", "content": "解读下面的安全事件："}]

message = send_messages(messages)
print(f"User>\t {messages[0]['content']}")

if message.tool_calls is not None:
    messages.append({'role': 'assistant', "content": "arguments='{\"product_name\":\"jetty\"}', name='get_threat_intelligence'"})
    tool = message.tool_calls[0]
    function_name = tool.function.name
    import json
    function_args = json.loads(tool.function.arguments)
    if function_name == 'get_threat_intelligence':
        # 提取参数并调用本地函数
        product_name = function_args.get('product_name')
        version = function_args.get('version')
        if product_name:
            result = get_threat_intelligence(product_name, version)
            messages.append({"role": "user", "content": result})
        else:
            print("缺少必要的参数：product_name")
    print(function_name)
    print(function_args)
else:
    messages.append()
# messages.append({"role": "tool", "tool_call_id": tool.id, "content": "24℃"})
message = send_messages(messages)
print(f"Model>\t {message.content}")
