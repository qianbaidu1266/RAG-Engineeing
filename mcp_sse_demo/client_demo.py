import asyncio
import json
import os
from typing import Optional
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.sse import sse_client
import openai
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()


class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.openai = openai.AsyncOpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.modelName = "qwen-plus"
        self.messages = []  # 多轮对话上下文

    async def connect_to_sse_server(self, server_url: str):
        self._streams_context = sse_client(url=server_url)
        streams = await self._streams_context.__aenter__()
        self._session_context = ClientSession(*streams)
        self.session: ClientSession = await self._session_context.__aenter__()
        await self.session.initialize()
        print("Initialized SSE client...")
        tools = (await self.session.list_tools()).tools
        print("Connected to server with tools:", [tool.name for tool in tools])

    async def cleanup(self):
        if self._session_context:
            await self._session_context.__aexit__(None, None, None)
        if self._streams_context:
            await self._streams_context.__aexit__(None, None, None)

    async def process_query(self, query: str) -> str:
        # 追加用户消息到上下文
        self.messages.append({"role": "user", "content": query})

        # 获取工具信息
        response = await self.session.list_tools()
        available_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        } for tool in response.tools]

        # 调用模型生成回复或工具调用
        completion = await self.openai.chat.completions.create(
            model=self.modelName ,
            max_tokens=1000,
            messages=self.messages,
            tools=available_tools
        )

        assistant_message = completion.choices[0].message
        final_text = []

        if assistant_message.tool_calls:
            # 工具调用逻辑
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                result = await self.session.call_tool(tool_name, tool_args)
                tool_output = result.content[0].text

                # 加入上下文
                self.messages.extend([
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tool_call]
                    },
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_output
                    }
                ])

                final_text.append(f"[Tool {tool_name} called with args {tool_args}]")
                final_text.append(f"[Tool returned]: {tool_output}")

            # 工具调用后续交互
            follow_up = await self.openai.chat.completions.create(
                model=self.modelName,
                max_tokens=1000,
                messages=self.messages
            )
            follow_up_content = follow_up.choices[0].message.content
            self.messages.append({"role": "assistant", "content": follow_up_content})
            final_text.append(follow_up_content)
        else:
            # 没有工具调用，直接助手回复
            content = assistant_message.content
            self.messages.append({"role": "assistant", "content": content})
            final_text.append(content)

        return "\n".join(final_text)

    async def chat_loop(self):
        print("\nMCP Client Started! Type your queries or 'quit' to exit.")
        while True:
            try:
                query = input("\nQuery: ").strip()
                if query.lower() == 'quit':
                    break
                response = await self.process_query(query)
                print("\n" + response)
            except Exception as e:
                print(f"\nError: {str(e)}")


async def main():
    client = MCPClient()
    try:
        server_url = "http://0.0.0.0:8020/sse"
        await client.connect_to_sse_server(server_url=server_url)
        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
