# -*- coding: utf-8 -*-
"""
上下文压缩模块
提供多种对话历史压缩策略，优化token使用和响应速度
"""

import json
import tiktoken
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum


class CompressionStrategy(Enum):
    """压缩策略枚举"""
    SLIDING_WINDOW = "sliding_window"  # 滑动窗口
    TOKEN_LIMIT = "token_limit"  # Token限制
    SMART_TRUNCATE = "smart_truncate"  # 智能截断
    SUMMARY = "summary"  # 摘要压缩
    HYBRID = "hybrid"  # 混合策略


@dataclass
class CompressionConfig:
    """压缩配置"""
    strategy: CompressionStrategy = CompressionStrategy.HYBRID
    max_messages: int = 20  # 最大消息数
    max_tokens: int = 6000  # 最大token数
    keep_system_prompt: bool = True  # 保留系统提示
    keep_recent_messages: int = 6  # 始终保留最近N条消息
    preserve_tool_calls: bool = True  # 保留工具调用上下文


class ContextCompressor:
    """上下文压缩器"""
    
    def __init__(self, config: Optional[CompressionConfig] = None):
        self.config = config or CompressionConfig()
        try:
            # 使用tiktoken计算token数量
            self.encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        except Exception:
            # 备用编码器
            self.encoding = tiktoken.get_encoding("cl100k_base")
    
    def count_tokens(self, text: str) -> int:
        """计算文本的token数量"""
        try:
            return len(self.encoding.encode(text))
        except Exception:
            # 简单估算：1 token ≈ 4 字符（中文约2字符）
            return len(text) // 3
    
    def count_message_tokens(self, message: Dict) -> int:
        """计算单条消息的token数量"""
        tokens = 0
        
        # 内容token
        if message.get("content"):
            tokens += self.count_tokens(str(message["content"]))
        
        # 工具调用token
        if message.get("tool_calls"):
            tokens += self.count_tokens(json.dumps(message["tool_calls"]))
        
        # 角色和其他元数据（估算）
        tokens += 4  # role, name等固定开销
        
        return tokens
    
    def count_messages_tokens(self, messages: List[Dict]) -> int:
        """计算消息列表的总token数"""
        return sum(self.count_message_tokens(msg) for msg in messages)
    
    def compress(self, messages: List[Dict]) -> List[Dict]:
        """根据配置的策略压缩消息"""
        if not messages:
            return messages
        
        strategy = self.config.strategy
        
        if strategy == CompressionStrategy.SLIDING_WINDOW:
            return self._sliding_window_compression(messages)
        elif strategy == CompressionStrategy.TOKEN_LIMIT:
            return self._token_limit_compression(messages)
        elif strategy == CompressionStrategy.SMART_TRUNCATE:
            return self._smart_truncate_compression(messages)
        elif strategy == CompressionStrategy.HYBRID:
            return self._hybrid_compression(messages)
        else:
            return messages
    
    def _sliding_window_compression(self, messages: List[Dict]) -> List[Dict]:
        """滑动窗口压缩：保留最近N条消息"""
        max_msgs = self.config.max_messages
        
        # 分离系统提示
        system_messages = [msg for msg in messages if msg.get("role") == "system"]
        other_messages = [msg for msg in messages if msg.get("role") != "system"]
        
        if self.config.keep_system_prompt and system_messages:
            # 保留系统提示 + 最近的消息
            return system_messages[:1] + other_messages[-max_msgs:]
        else:
            return other_messages[-max_msgs:]
    
    def _token_limit_compression(self, messages: List[Dict]) -> List[Dict]:
        """基于Token限制的压缩"""
        max_tokens = self.config.max_tokens
        
        # 分离系统提示
        system_messages = [msg for msg in messages if msg.get("role") == "system"]
        other_messages = [msg for msg in messages if msg.get("role") != "system"]
        
        result = []
        current_tokens = 0
        
        # 添加系统提示
        if self.config.keep_system_prompt and system_messages:
            system_msg = system_messages[0]
            system_tokens = self.count_message_tokens(system_msg)
            result.append(system_msg)
            current_tokens += system_tokens
        
        # 从最新消息开始反向添加
        for msg in reversed(other_messages):
            msg_tokens = self.count_message_tokens(msg)
            if current_tokens + msg_tokens <= max_tokens:
                result.insert(1 if result and result[0].get("role") == "system" else 0, msg)
                current_tokens += msg_tokens
            else:
                break
        
        return result
    
    def _smart_truncate_compression(self, messages: List[Dict]) -> List[Dict]:
        """智能截断：保留重要消息"""
        # 分离不同类型的消息
        system_messages = []
        tool_related = []
        recent_messages = []
        other_messages = []
        
        keep_recent = self.config.keep_recent_messages
        
        for i, msg in enumerate(messages):
            role = msg.get("role")
            
            if role == "system":
                system_messages.append(msg)
            elif i >= len(messages) - keep_recent:
                # 最近的消息
                recent_messages.append(msg)
            elif self.config.preserve_tool_calls and (
                role == "tool" or msg.get("tool_calls")
            ):
                # 工具相关消息
                tool_related.append(msg)
            else:
                other_messages.append(msg)
        
        # 组合结果
        result = []
        
        if self.config.keep_system_prompt and system_messages:
            result.extend(system_messages[:1])
        
        # 添加工具相关消息（采样）
        if tool_related:
            # 只保留最近的工具调用
            result.extend(tool_related[-4:])
        
        # 添加其他消息（采样）
        if other_messages:
            # 均匀采样
            step = max(1, len(other_messages) // 3)
            result.extend(other_messages[::step][-3:])
        
        # 添加最近消息
        result.extend(recent_messages)
        
        return result
    
    def _hybrid_compression(self, messages: List[Dict]) -> List[Dict]:
        """混合策略：结合多种方法"""
        # 第一步：智能截断
        compressed = self._smart_truncate_compression(messages)
        
        # 第二步：检查token数量
        total_tokens = self.count_messages_tokens(compressed)
        
        if total_tokens > self.config.max_tokens:
            # 如果还是超过限制，使用token限制压缩
            compressed = self._token_limit_compression(compressed)
        
        # 第三步：检查消息数量
        if len(compressed) > self.config.max_messages:
            compressed = self._sliding_window_compression(compressed)
        
        return compressed
    
    def get_compression_stats(self, original: List[Dict], compressed: List[Dict]) -> Dict:
        """获取压缩统计信息"""
        original_count = len(original)
        compressed_count = len(compressed)
        original_tokens = self.count_messages_tokens(original)
        compressed_tokens = self.count_messages_tokens(compressed)
        
        return {
            "original_messages": original_count,
            "compressed_messages": compressed_count,
            "messages_reduced": original_count - compressed_count,
            "reduction_rate": f"{((original_count - compressed_count) / original_count * 100):.1f}%" if original_count > 0 else "0%",
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "tokens_saved": original_tokens - compressed_tokens,
            "token_reduction_rate": f"{((original_tokens - compressed_tokens) / original_tokens * 100):.1f}%" if original_tokens > 0 else "0%"
        }


class SummaryCompressor(ContextCompressor):
    """基于摘要的压缩器（需要LLM支持）"""
    
    def __init__(self, config: Optional[CompressionConfig] = None, llm_client=None):
        super().__init__(config)
        self.llm_client = llm_client
    
    async def _summarize_messages(self, messages: List[Dict]) -> str:
        """使用LLM总结历史消息"""
        if not self.llm_client:
            return "历史对话摘要"
        
        # 构建摘要提示
        conversation_text = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in messages
            if msg.get("content")
        ])
        
        summary_prompt = f"""请简洁总结以下对话的关键信息和上下文，保留重要事实：

{conversation_text}

摘要（100字以内）："""
        
        try:
            response = await self.llm_client.chat.completions.create(
                model="qwen-turbo",
                messages=[{"role": "user", "content": summary_prompt}],
                max_tokens=200
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"❌ 摘要生成失败: {e}")
            return "历史对话摘要"
    
    async def compress_with_summary(self, messages: List[Dict]) -> List[Dict]:
        """使用摘要压缩旧消息"""
        if len(messages) <= self.config.keep_recent_messages + 1:
            return messages
        
        # 分离消息
        system_messages = [msg for msg in messages if msg.get("role") == "system"]
        other_messages = [msg for msg in messages if msg.get("role") != "system"]
        
        keep_recent = self.config.keep_recent_messages
        old_messages = other_messages[:-keep_recent]
        recent_messages = other_messages[-keep_recent:]
        
        # 总结旧消息
        summary = await self._summarize_messages(old_messages)
        summary_message = {
            "role": "system",
            "content": f"[历史对话摘要]: {summary}"
        }
        
        # 组合结果
        result = []
        if self.config.keep_system_prompt and system_messages:
            result.append(system_messages[0])
        result.append(summary_message)
        result.extend(recent_messages)
        
        return result


# 便捷函数
def create_compressor(
    strategy: str = "hybrid",
    max_messages: int = 20,
    max_tokens: int = 6000,
    **kwargs
) -> ContextCompressor:
    """创建压缩器的便捷函数"""
    try:
        strategy_enum = CompressionStrategy(strategy)
    except ValueError:
        strategy_enum = CompressionStrategy.HYBRID
    
    config = CompressionConfig(
        strategy=strategy_enum,
        max_messages=max_messages,
        max_tokens=max_tokens,
        **kwargs
    )
    
    return ContextCompressor(config)


# 使用示例
if __name__ == "__main__":
    # 测试压缩器
    test_messages = [
        {"role": "system", "content": "你是一个智能助手"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "您好！有什么可以帮您的吗？"},
        {"role": "user", "content": "今天天气怎么样？"},
        {"role": "assistant", "tool_calls": [{"id": "1", "function": {"name": "get_weather"}}]},
        {"role": "tool", "content": '{"weather": "晴"}'},
        {"role": "assistant", "content": "今天天气晴朗"},
    ] * 5  # 模拟长对话
    
    # 创建压缩器
    compressor = create_compressor(
        strategy="hybrid",
        max_messages=10,
        max_tokens=2000
    )
    
    # 压缩
    compressed = compressor.compress(test_messages)
    
    # 统计
    stats = compressor.get_compression_stats(test_messages, compressed)
    
    print("=" * 50)
    print("压缩统计:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print("=" * 50)
    print(f"\n原始消息数: {len(test_messages)}")
    print(f"压缩后消息数: {len(compressed)}")

