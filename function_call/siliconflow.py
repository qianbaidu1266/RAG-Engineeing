import requests

url = "https://api.siliconflow.cn/v1/chat/completions"

api_key = "sk-dcfllghprbwqvgyamiiqqpjqkmdqcrlxogifvioebizyfxgu"

payload = {
    "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
    "messages": [
        {
            "role": "user",
            "content": "1+1等于几"
        }
    ],
    "stream": True,
    "max_tokens": 512,
    "stop": ["null"],
    "temperature": 0.7,
    "top_p": 0.7,
    "top_k": 50,
    "frequency_penalty": 0.5,
    "n": 1,
    "response_format": {"type": "text"},
    "tools": [
        {
            "type": "function",
            "function": {
                "description": "<string>",
                "name": "<string>",
                "parameters": {},
                "strict": False
            }
        }
    ]
}
headers = {
    "Authorization": "Bearer " + api_key,
    "Content-Type": "application/json"
}

response = requests.request("POST", url, json=payload, headers=headers)

print(response.text)