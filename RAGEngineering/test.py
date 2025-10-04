import os
import json
import asyncio
import traceback
import time
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from openai import OpenAI
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import create_engine, Column, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

# ================== 初始化 ==================
app = FastAPI(title="优化工具链调用-长短期记忆管理")

# 配置数据库连接
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MYSQL_URL = os.getenv("MYSQL_URL", "mysql+pymysql://root:password@localhost/rag")

# 初始化Redis和MySQL
redis_client = Redis.from_url(REDIS_URL)
engine = create_engine(MYSQL_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 初始化OpenAI客户端
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 常量定义
MAX_SHORT_TERM_MESSAGES = 10  # Redis短期记忆保存的消息数
MESSAGE_COMPRESSION_THRESHOLD = 15  # 消息压缩阈值
REDIS_SESSION_TTL = 3600  # 会话在Redis中的存活时间(秒)
SESSION_CLEANUP_INTERVAL = 60 * 5  # 会话清理间隔(秒) - 5分钟
MODEL_NAME = "qwen-plus"


# ================== 数据库模型 ==================
class ConversationMemory(Base):
    __tablename__ = "chat_history"

    id = Column(String(255), primary_key=True, index=True)
    conversation_id = Column(String(255), index=True)
    role = Column(String(50))
    content = Column(Text)
    created_at = Column(DateTime, default=func.now())

Base.metadata.create_all(bind=engine)


# ================== 请求模型 ==================
class QueryRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None


# ================== 记忆管理类 ==================
class MemoryManager:
    @staticmethod
    def generate_conversation_id() -> str:
        """生成唯一的会话ID"""
        timestamp = int(time.time() * 1000)
        random_uuid = uuid.uuid4().hex
        return f"{timestamp}_{random_uuid}"

    @staticmethod
    async def save_to_redis(conversation_id: str, messages: List[Dict]):
        """将消息保存到Redis（短期存储）"""
        try:
            # 使用哈希存储会话历史
            pipeline = redis_client.pipeline()
            pipeline.delete(f"conversation:{conversation_id}:messages")

            # 存储完整消息历史
            for i, message in enumerate(messages[-MAX_SHORT_TERM_MESSAGES:]):
                pipeline.hset(
                    f"conversation:{conversation_id}:messages",
                    f"msg_{i}",
                    json.dumps(message)
                )

            # 存储最后活跃时间并设置过期时间
            pipeline.set(f"conversation:{conversation_id}:last_active", time.time())
            pipeline.expire(f"conversation:{conversation_id}:messages", REDIS_SESSION_TTL)
            pipeline.expire(f"conversation:{conversation_id}:last_active", REDIS_SESSION_TTL)
            pipeline.execute()
        except Exception as e:
            app.logger.error(f"Redis保存失败: {str(e)}")

    @staticmethod
    async def save_to_mysql(conversation_id: str, messages: List[Dict]):
        """异步将消息保存到MySQL（长期存储）"""
        try:
            db = SessionLocal()
            for message in messages:
                # 检查是否是摘要消息
                is_summary = "summary_token" in message.get("metadata", {})

                db_message = ConversationMemory(
                    id=f"{conversation_id}-{message['role']}-{time.time()}",
                    conversation_id=conversation_id,
                    role=message["role"],
                    content=message["content"],
                    created_at=datetime.now(),
                    is_compressed=False,
                    is_summary=is_summary,
                    is_active=True
                )
                db.add(db_message)
            db.commit()
        except Exception as e:
            traceback.print_exc()
            app.logger.error(f"MySQL保存失败: {str(e)}")
        finally:
            db.close()

    @staticmethod
    def get_from_redis(conversation_id: str) -> Optional[List[Dict]]:
        """从Redis获取短期记忆"""
        try:
            message_keys = redis_client.hkeys(f"conversation:{conversation_id}:messages")
            if not message_keys:
                return None

            messages = []
            for key in sorted(message_keys):
                message_data = redis_client.hget(f"conversation:{conversation_id}:messages", key)
                messages.append(json.loads(message_data))

            # 更新最后活跃时间
            redis_client.set(f"conversation:{conversation_id}:last_active", time.time())
            return messages
        except Exception:
            return None

    @staticmethod
    def get_from_mysql(conversation_id: str) -> Optional[List[Dict]]:
        """从MySQL获取长期记忆"""
        try:
            db = SessionLocal()
            memories = db.query(ConversationMemory).filter(
                ConversationMemory.conversation_id == conversation_id,
                ConversationMemory.is_active.is_(True)
            ).order_by(ConversationMemory.created_at.asc()).all()

            return [
                {
                    "role": m.role,
                    "content": m.content,
                    "is_compressed": m.is_compressed,
                    "is_summary": m.is_summary
                }
                for m in memories
            ]
        except Exception as e:
            traceback.print_exc()
            return None
        finally:
            db.close()

    @staticmethod
    def compress_messages(conversation_id: str, messages: List[Dict]) -> List[Dict]:
        """压缩过多的消息历史"""
        try:
            # 如果消息数量小于阈值，直接返回
            if len(messages) < MESSAGE_COMPRESSION_THRESHOLD:
                return messages

            app.logger.info(f"压缩会话历史: {conversation_id} (原消息数: {len(messages)})")

            # 将消息分成两部分：需要压缩的旧消息和保留的最新消息
            split_index = max(len(messages) - MAX_SHORT_TERM_MESSAGES, 0)
            to_compress = messages[:split_index]
            to_keep = messages[split_index:]

            # 生成摘要 (简化实现)
            summary = "先前对话摘要: "
            for msg in to_compress:
                if msg["role"] in ["user", "assistant"]:
                    summary += f"{msg['role']}: {msg['content']}; "
                if len(summary) > 200:  # 简单截断
                    summary = summary[:197] + "..."
                    break

            # 创建摘要消息
            summary_msg = {
                "role": "system",
                "content": summary,
                "metadata": {
                    "summary_token": True,
                    "compressed_count": len(to_compress)
                }
            }

            # 在MySQL中标记旧消息为已压缩
            db = SessionLocal()
            for msg in to_compress:
                db.query(ConversationMemory).filter(
                    ConversationMemory.conversation_id == conversation_id,
                    ConversationMemory.content == msg.get("content")
                ).update({"is_compressed": True})
            db.commit()

            # 构建压缩后的消息历史
            compressed_history = [summary_msg] + to_keep

            app.logger.info(f"压缩完成: 新消息数: {len(compressed_history)}")
            return compressed_history
        except Exception as e:
            traceback.print_exc()
            app.logger.error(f"压缩失败: {str(e)}")
            return messages  # 返回原始消息


# ================== 会话管理定时任务 ==================
async def clean_inactive_sessions():
    """定期清理Redis中的非活跃会话"""
    try:
        app.logger.info("执行会话清理任务...")

        # 查找所有会话键
        keys = redis_client.keys("conversation:*:last_active")

        for key in keys:
            last_active = float(redis_client.get(key))
            inactive_duration = time.time() - last_active

            if inactive_duration > REDIS_SESSION_TTL:
                # 提取会话ID
                conversation_id = key.decode().split(":")[1]

                # 删除相关键
                redis_client.delete(key)
                redis_client.delete(f"conversation:{conversation_id}:messages")

                # 在MySQL中标记为非活跃
                db = SessionLocal()
                db.query(ConversationMemory).filter(
                    ConversationMemory.conversation_id == conversation_id
                ).update({"is_active": False})
                db.commit()

                app.logger.info(f"清理非活跃会话: {conversation_id}")

        app.logger.info(f"会话清理完成, 处理了 {len(keys)} 个会话")
    except Exception as e:
        app.logger.error(f"清理任务错误: {str(e)}")


# ================== 对话流程 ==================
system_prompt = """你是一个智能助手，需要根据问题类型选择合适工具获取信息。可用工具包括：
1. 城市编码查询工具（get_city_code）- 根据城市名称查询城市编码
2. 天气查询工具（get_weather）- 根据编码查询所在地的天气情况
3. 天气预测功能（get_weather_forecast）- 根据城市名称预测未来几天的天气情况"""


@app.post("/query")
async def query_endpoint(
        request: QueryRequest,
        background_tasks: BackgroundTasks
):
    try:
        # 1. 创建或获取会话ID
        conversation_id = request.conversation_id or MemoryManager.generate_conversation_id()

        # 2. 获取历史记录 (优先从Redis获取)
        messages = MemoryManager.get_from_redis(conversation_id)

        # 3. 如果Redis中没有，从MySQL加载
        if not messages:
            messages = MemoryManager.get_from_mysql(conversation_id)

            # 如果加载的历史记录过长，进行压缩
            if messages and len(messages) > MESSAGE_COMPRESSION_THRESHOLD:
                messages = MemoryManager.compress_messages(conversation_id, messages)

        # 4. 如果仍然没有历史记录，初始化
        if not messages:
            messages = []

        # 5. 检查系统提示是否已存在
        has_system_prompt = any(m["role"] == "system" for m in messages)
        if not has_system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 6. 添加用户新查询
        messages.append({"role": "user", "content": request.query})

        # 7. 构建完整的对话历史（这里简化了实际的AI调用）
        # 在实际应用中，您会在这里调用AI模型生成响应
        ai_response = f"这是对查询 '{request.query}' 的响应 (会话ID: {conversation_id})"
        messages.append({"role": "assistant", "content": ai_response})

        # 8. 保存到短期存储 (Redis)
        background_tasks.add_task(
            MemoryManager.save_to_redis,
            conversation_id,
            messages
        )

        # 9. 异步保存到长期存储 (MySQL)
        background_tasks.add_task(
            MemoryManager.save_to_mysql,
            conversation_id,
            messages
        )

        return {
            "conversation_id": conversation_id,
            "response": ai_response,
            "message_count": len(messages),
            "is_compressed": len(messages) > MESSAGE_COMPRESSION_THRESHOLD
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================== 启动定时任务 ==================
@app.on_event("startup")
async def startup_event():
    scheduler = AsyncIOScheduler()
    # 每5分钟运行一次清理任务
    scheduler.add_job(
        clean_inactive_sessions,
        'interval',
        seconds=SESSION_CLEANUP_INTERVAL
    )
    scheduler.start()
    app.logger.info("会话清理定时任务已启动")


# ================== 主程序 ==================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)