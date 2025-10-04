import json
import re


def clean_json_string(s):
    """
    清理JSON字符串中的非法控制字符

    参数:
        s (str): 原始JSON字符串

    返回:
        str: 清理后的字符串
    """
    # 替换非法控制字符(0x00-0x1F)，但保留合法控制字符(\t, \n, \r)
    return re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', s)


def robust_json_parse(json_str, max_retries=3):
    """
    健壮的JSON解析函数，尝试多种方式处理非法字符

    参数:
        json_str (str): JSON格式的字符串
        max_retries (int): 最大尝试次数

    返回:
        list: 解析后的数据
    """
    attempts = 0
    while attempts < max_retries:
        try:
            # 直接尝试解析
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            attempts += 1

            if 'Invalid control character' in str(e) or 'control character' in str(e):
                # 清理非法控制字符后重试
                json_str = clean_json_string(json_str)
                continue
            elif 'Expecting value' in str(e) or 'Unterminated string' in str(e):
                # 尝试修复未闭合的引号
                json_str = re.sub(r'(?<!\\)"([^"]*)$', r'"\1"', json_str)
                json_str = re.sub(r'^([^"]*)"', r'"\1"', json_str)
                continue
            elif 'Extra data' in str(e):
                # 尝试修复多余逗号
                json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
                continue
            else:
                # 尝试修复无效转义字符
                json_str = re.sub(r'\\(?![\\/"bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', json_str)
                continue

    # 如果所有尝试都失败，返回空列表
    print(f"JSON解析失败，尝试{max_retries}次后仍无法解析")
    return []


def filter_fqa_by_types(json_str, filter_types):
    """
    从JSON字符串中过滤出包含任何指定类型的FAQ对

    参数:
        json_str (str): 包含FAQ数据的JSON字符串
        filter_types (list): 需要筛选的目标类型列表（如["问候", "告别"]）

    返回:
        list: 符合条件FAQ字典组成的列表
    """
    # 1. 健壮解析JSON数据
    try:
        # 尝试直接解析
        fqa_list = json.loads(json_str)
    except json.JSONDecodeError:
        # 如果直接解析失败，使用健壮解析方法
        fqa_list = robust_json_parse(json_str)

    # 2. 确保我们有可用的FAQ列表
    if not isinstance(fqa_list, list):
        print(f"解析结果不是列表类型，而是 {type(fqa_list)}")
        return []

    # 3. 确保filter_types是列表格式
    if isinstance(filter_types, str):
        filter_types = [t.strip() for t in filter_types.split(',') if t.strip()]

    elif isinstance(filter_types, (list, tuple, set)):
        filter_types = [str(t) for t in filter_types]
    else:
        print(f"filter_types 必须是字符串、列表或元组")
        return []

    # 4. 筛选包含任何指定类型的FAQ对
    filtered_data = []
    for item in fqa_list:
        # 跳过无效项
        if not isinstance(item, dict):
            continue

        # 获取项目中的类型字段
        item_type = item.get("type", "")

        # 拆分可能存在的多个类型
        # 支持中英文逗号、分号、竖线等多种分隔符
        if isinstance(item_type, str) and item_type:
            item_types = re.split(r'[，,;|/]', item_type)
            item_types = [t.strip() for t in item_types if t.strip()]
        else:
            # 如果类型字段缺失或非字符串，跳过
            continue

        # 检查是否包含任何目标类型
        if any(target_type in item_types for target_type in filter_types):
            filtered_data.append(item)

    return filtered_data


# 示例用法
if __name__ == "__main__":
    # 示例JSON字符串包含非法控制字符
    json_data = r'''
    [
        {"question": "你好", "answer": "你好，\0有什么可以帮助您的", "type": "问候"},
        {"question": "如何退货？", "answer": "7天内可无理由退货\n**", "type": "售后\x0b物流"},
        {"question": "运费多少？", "answer": "满99包邮", "type": "物流,价格"},
        {"question": "再见", "answer": "期待再次为您服务", "type": "告别"},
        {"question": "优惠活动", "answer": "查看官网最新\1活动", "type": "促销"}
    ]
    '''

    print("原始JSON字符串中检测到非法控制字符：")
    for i, char in enumerate(json_data):
        if ord(char) < 32 and char not in '\t\n\r':
            print(f"位置 {i}: 0x{ord(char):02x} (非法控制字符)")

    # 筛选包含"物流"或"告别"类型的FAQ
    target_types = ["物流", "告别"]
    result = filter_fqa_by_types(json_data, target_types)

    print(f"\n包含 {target_types} 类型的FAQ:")
    for i, item in enumerate(result):
        # 清理回答中的控制字符
        cleaned_answer = clean_json_string(item["answer"])
        print(f"{i + 1}. 问题: {item['question']} | 回答: {cleaned_answer} | 类型: {item['type']}")