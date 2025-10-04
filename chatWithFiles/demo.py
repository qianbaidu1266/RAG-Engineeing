try:
    # 异步调用大模型
    response = await client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.2,
        stream=True  # 启用流式
    )

    # 解析流式响应
    collected_answer = ""
    think_tag_detected = False  # 标记是否遇到</think>
    post_think_tokens = []  # 缓冲</think>后的token
    function_check_done = False  # 是否完成前三token检查
    function_mode = False  # 是否进入函数调用模式

    async for chunk in response:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta

        if hasattr(delta, "content"):
            content = delta.content

            # 未遇到</think>时的处理
            if not think_tag_detected:
                if "</think>" in content:
                    think_tag_detected = True
                    parts = content.split("</think>", 1)

                    # 发送前半部分+</think>
                    temp = {
                        "event": "message",
                        "conversation_id": conversation_id,
                        "answer": parts[0] + "</think>"
                    }
                    yield f"data: {json.dumps(temp)}\n\n"

                    # 缓存剩余内容
                    if parts[1]:
                        post_think_tokens.append(parts[1])
                else:
                    # 直接转发内容
                    temp = {
                        "event": "message",
                        "conversation_id": conversation_id,
                        "answer": content
                    }
                    yield f"data: {json.dumps(temp)}\n\n"

            # 已遇到</think>后的处理
            else:
                if not function_check_done:
                    post_think_tokens.append(content)

                    # 检查前10个token判断函数调用
                    if len(post_think_tokens) >= 10:
                        combined = "".join(post_think_tokens[:10])
                        if combined.lstrip().startswith("...") and "tool" in combined:
                            function_mode = True
                            function_check_done = True
                            post_think_tokens = []
                else:
                    if function_mode:
                        # 函数调用模式处理
                        post_think_tokens.append(content)
                        code_block = "".join(post_think_tokens)

                        if code_block.count("```") >= 2:
                            try:
                                # 提取JSON参数
                                function_json_str = code_block.split("```", 2)[1]
                                tool_info = json.loads(function_json_str.split("json")[1])

                                # 发送文档检索提示
                                chunk_data = {
                                    "event": "message",
                                    "conversation_id": conversation_id,
                                    "answer": f"<think>正在检索文档{tool_info['file_list']}</think>"
                                }
                                yield f"data: {json.dumps(chunk_data)}\n\n"

                                # 执行二次大模型调用
                                async for answer_chunk in answer_with_lm(tool_info, query, conversation_id):
                                    yield answer_chunk

                            except json.JSONDecodeError as e:
                                print(f"JSON解析失败: {e}")
                                return
                    else:
                        # 直接转发后续内容
                        temp = {
                            "event": "message",
                            "conversation_id": conversation_id,
                            "answer": content
                        }
                        yield f"data: {json.dumps(temp)}\n\n"

        # 流式结束处理
        if choice.finish_reason == "stop":
            temp = {
                "event": "message_end",
                "conversation_id": conversation_id,
                "answer": ""
            }
            yield f"data: {json.dumps(temp)}\n\n"
            break

except Exception as e:
    print(f"匹配阶段失败，conversation_id:{conversation_id},e:{e}")
finally:
    print(f"匹配阶段完成，conversation_id={conversation_id}")



def answer_with_llm(data: dict, request: QueryRequest):
    """第二次调用：读取匹配文档，并调用大模型"""
    query = request.query
    conversation_id = request.conversation_id
    # 获取当前对话历史（如果不存在则创建）
    #messages = answer_history.setdefault(conversation_id, [])
    messages = get_or_create_conversation_history(conversation_id, "answer", answer_history)
    files = data.get('matched_files', [])
    relate_info = ""
    for file in files:
        relate_info += file + ":\n" + read_pdf(file) + "\n\n"

    # 生成问题+相关文档的提示词
    answer_prompt = f"""
    你是一个制度问答智能助手，请根据制度文档参考信息简洁专业地回答用户问题：
    回答策略：
    1.如果制度文档参考信息为空，提示用户没有找到相关的制度文档，引导用户问具体的制度方面的问题。
    2.透明化操作：在处理用户请求过程中，如果参考了制度文档的信息，简要告知用户制度文档的名称，增加信息来源的透明度和可信度。
    3.确认与跟进：解答完毕后，确认用户是否满意解答，并主动询问是否有其他可以帮助的地方，如：“请问还有其他问题需要我的帮助吗？”
    """
    # 确保 system prompt 只添加一次
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": answer_prompt})
    # **合并参考信息与用户问题**
    combined_query = f"用户问题：{query}\n参考文档信息：\n{relate_info}"
    # 添加当前用户的提问
    messages.append({"role": "user", "content": combined_query})
    save_message("answer", conversation_id, "user", combined_query)

    try:
        # 3. 调用大模型
        # 使用异步方式调用模型
        response = client.chat.completions.create(
                                           model=model_name,
                                           messages=messages,
                                           temperature=0.7,
                                           stream=True  # 启用流式响应
                                           )
        # 4. 解析结果
        answer = ""
        for chunk in response:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if hasattr(delta, "content"):
                content = delta.content
                answer += content
                if choice.finish_reason == "stop":
                    symbol = "message_end"
                else:
                    symbol = "message"
                temp = {"event": symbol,"stage":"answer","conversation_id": conversation_id,"content": content}
                print(f"response:{temp}")
                # 将字典转换为 JSON 字符串并添加换行符
                yield json.dumps(temp) + "\n"  # 返回字符串类型
            if choice.finish_reason == "stop":
                messages.append({"role": "assistant", "content": answer})
                save_message("answer", conversation_id, "assistant", answer)
                answer_history[conversation_id] = messages
                print(f"""answer回答结果：{answer}""")
                break
    except Exception as e:
        yield json.dumps({"status": "error", "message": str(e)})
