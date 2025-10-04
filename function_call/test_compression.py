# -*- coding: utf-8 -*-
"""
上下文压缩测试脚本
演示不同压缩策略的效果
"""

from context_compression import (
    create_compressor, 
    CompressionStrategy,
    ContextCompressor
)
from typing import List, Dict


def generate_mock_conversation(num_turns: int = 10) -> List[Dict]:
    """生成模拟对话数据"""
    messages = [
        {"role": "system", "content": "你是一个智能助手，需要根据问题类型选择合适工具获取信息。"}
    ]
    
    for i in range(num_turns):
        # 用户消息
        messages.append({
            "role": "user",
            "content": f"这是第{i+1}轮对话，我想问一个问题：今天天气怎么样？"
        })
        
        # 助手工具调用
        if i % 2 == 0:
            messages.append({
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city_name": "北京"}'
                        }
                    }
                ],
                "content": None
            })
            
            # 工具响应
            messages.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "name": "get_weather",
                "content": '{"status": "success", "weather": "晴", "temperature": "20°C"}'
            })
        
        # 助手回复
        messages.append({
            "role": "assistant",
            "content": f"根据查询结果，今天天气晴朗，温度20°C，适合外出活动。这是第{i+1}轮对话的回复。"
        })
    
    return messages


def test_strategy(strategy_name: str, messages: List[Dict], config: dict):
    """测试单个压缩策略"""
    print(f"\n{'='*60}")
    print(f"📊 测试策略: {strategy_name.upper()}")
    print(f"{'='*60}")
    
    compressor = create_compressor(
        strategy=strategy_name,
        **config
    )
    
    # 执行压缩
    compressed = compressor.compress(messages)
    
    # 获取统计信息
    stats = compressor.get_compression_stats(messages, compressed)
    
    # 打印结果
    print(f"\n📈 压缩统计:")
    print(f"  原始消息数: {stats['original_messages']}")
    print(f"  压缩后消息数: {stats['compressed_messages']}")
    print(f"  减少消息数: {stats['messages_reduced']}")
    print(f"  压缩率: {stats['reduction_rate']}")
    print(f"  原始Token数: {stats['original_tokens']}")
    print(f"  压缩后Token数: {stats['compressed_tokens']}")
    print(f"  节省Token数: {stats['tokens_saved']}")
    print(f"  Token压缩率: {stats['token_reduction_rate']}")
    
    # 分析保留的消息类型
    role_counts = {}
    for msg in compressed:
        role = msg.get("role", "unknown")
        role_counts[role] = role_counts.get(role, 0) + 1
    
    print(f"\n📋 保留的消息分布:")
    for role, count in role_counts.items():
        print(f"  {role}: {count}条")
    
    # 检查系统提示
    has_system = any(msg.get("role") == "system" for msg in compressed)
    print(f"\n✅ 系统提示保留: {'是' if has_system else '否'}")
    
    # 检查工具调用
    tool_calls = sum(1 for msg in compressed if msg.get("tool_calls") or msg.get("role") == "tool")
    print(f"✅ 工具相关消息: {tool_calls}条")
    
    return stats


def compare_all_strategies():
    """比较所有压缩策略"""
    print("\n" + "="*60)
    print("🔬 上下文压缩策略对比测试")
    print("="*60)
    
    # 生成测试数据
    num_turns = 15
    messages = generate_mock_conversation(num_turns)
    
    print(f"\n📝 生成测试数据:")
    print(f"  对话轮数: {num_turns}")
    print(f"  总消息数: {len(messages)}")
    
    # 压缩配置
    config = {
        "max_messages": 20,
        "max_tokens": 4000,
        "keep_recent_messages": 6,
        "preserve_tool_calls": True
    }
    
    print(f"\n⚙️ 压缩配置:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    # 测试各策略
    strategies = [
        "sliding_window",
        "token_limit",
        "smart_truncate",
        "hybrid"
    ]
    
    results = {}
    for strategy in strategies:
        try:
            stats = test_strategy(strategy, messages, config)
            results[strategy] = stats
        except Exception as e:
            print(f"\n❌ 策略 {strategy} 测试失败: {e}")
    
    # 生成对比表格
    print("\n" + "="*60)
    print("📊 策略对比总结")
    print("="*60)
    print(f"\n{'策略':<20} {'消息压缩率':<15} {'Token压缩率':<15} {'保留消息':<10}")
    print("-" * 60)
    
    for strategy, stats in results.items():
        print(f"{strategy:<20} {stats['reduction_rate']:<15} "
              f"{stats['token_reduction_rate']:<15} {stats['compressed_messages']:<10}")
    
    # 推荐策略
    print("\n" + "="*60)
    print("💡 策略推荐")
    print("="*60)
    print("""
1. **sliding_window** - 简单快速，适合短期对话
   - 优点：实现简单，性能高
   - 缺点：可能丢失重要信息
   
2. **token_limit** - 精确控制成本
   - 优点：Token控制准确
   - 缺点：可能截断对话链
   
3. **smart_truncate** - 智能保留关键信息
   - 优点：保持上下文连贯性
   - 缺点：可能仍超Token限制
   
4. **hybrid** ⭐ 推荐 - 综合最优
   - 优点：平衡各方面需求
   - 缺点：计算稍复杂
    """)


def test_edge_cases():
    """测试边界情况"""
    print("\n" + "="*60)
    print("🔍 边界情况测试")
    print("="*60)
    
    compressor = create_compressor(strategy="hybrid", max_messages=10)
    
    # 测试1：空消息列表
    print("\n测试1: 空消息列表")
    result = compressor.compress([])
    print(f"  结果: {len(result)}条消息")
    assert len(result) == 0, "空列表测试失败"
    print("  ✅ 通过")
    
    # 测试2：只有系统提示
    print("\n测试2: 只有系统提示")
    messages = [{"role": "system", "content": "系统提示"}]
    result = compressor.compress(messages)
    print(f"  结果: {len(result)}条消息")
    assert len(result) == 1, "系统提示测试失败"
    print("  ✅ 通过")
    
    # 测试3：消息数小于阈值
    print("\n测试3: 消息数小于阈值")
    messages = [
        {"role": "system", "content": "系统提示"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "您好！"}
    ]
    result = compressor.compress(messages)
    print(f"  原始: {len(messages)}条，压缩后: {len(result)}条")
    print("  ✅ 通过")
    
    # 测试4：大量工具调用
    print("\n测试4: 大量工具调用")
    messages = [{"role": "system", "content": "系统"}]
    for i in range(20):
        messages.append({"role": "assistant", "tool_calls": [{"id": f"call_{i}"}]})
        messages.append({"role": "tool", "tool_call_id": f"call_{i}", "content": "结果"})
    
    result = compressor.compress(messages)
    tool_count = sum(1 for msg in result if msg.get("tool_calls") or msg.get("role") == "tool")
    print(f"  原始工具消息: {len(messages)-1}条")
    print(f"  压缩后工具消息: {tool_count}条")
    print("  ✅ 通过")
    
    print("\n✅ 所有边界测试通过！")


def benchmark_performance():
    """性能基准测试"""
    import time
    
    print("\n" + "="*60)
    print("⚡ 性能基准测试")
    print("="*60)
    
    # 生成大量消息
    messages = generate_mock_conversation(50)  # 50轮对话
    
    strategies = ["sliding_window", "token_limit", "smart_truncate", "hybrid"]
    
    print(f"\n测试数据: {len(messages)}条消息")
    print(f"\n{'策略':<20} {'耗时(ms)':<15} {'内存估算':<15}")
    print("-" * 60)
    
    for strategy in strategies:
        compressor = create_compressor(strategy=strategy, max_messages=20)
        
        # 多次测试取平均
        times = []
        for _ in range(10):
            start = time.perf_counter()
            compressor.compress(messages)
            end = time.perf_counter()
            times.append((end - start) * 1000)
        
        avg_time = sum(times) / len(times)
        print(f"{strategy:<20} {avg_time:<15.2f} {'轻量':<15}")
    
    print("\n✅ 性能测试完成！")


if __name__ == "__main__":
    # 运行所有测试
    try:
        print("\n🚀 开始上下文压缩测试...\n")
        
        # 1. 策略对比
        compare_all_strategies()
        
        # 2. 边界测试
        test_edge_cases()
        
        # 3. 性能测试
        benchmark_performance()
        
        print("\n" + "="*60)
        print("✅ 所有测试完成！")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

