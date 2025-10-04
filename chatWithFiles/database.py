import os
import json
import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from collections import namedtuple

# 加载环境变量
load_dotenv("dev.env")  # 加载开发环境配置

# 读取环境变量中的数据库 URL
DB_URL = os.getenv("DATABASE_URL")

# 创建数据库连接
engine = create_engine(DB_URL, echo=True)
Base = declarative_base()


# 定义消息表（表名改为 chat_history）
class ChatHistory(Base):
    __tablename__ = "chat_history"  # 表名改为 chat_history
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(255), nullable=False)  # 会话ID
    task_type = Column(String(50), nullable=False) # 任务类型 match 或 answer
    role = Column(String(50), nullable=False)  # 角色（user, assistant, system）
    content = Column(Text, nullable=False)  # 消息内容
    created_at = Column(DateTime, default=datetime.datetime.utcnow)  # 创建时间

# 创建表（如果表不存在的话）
Base.metadata.create_all(engine)

# 创建会话（Session）实例
Session = sessionmaker(bind=engine)
session = Session()

# 存储消息到数据库
def save_message(task_type, conversation_id, role, content):
    try:
        message = ChatHistory(
            task_type=task_type,
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=datetime.datetime.utcnow()
        )
        session.add(message)
        session.commit()
    except Exception as e:
        print(f"保存消息失败: {e}")
        session.rollback()

def get_messages_from_db(conversation_id, tasktype=None):
    try:
        # 构造查询语句
        query = session.query(ChatHistory.role,ChatHistory.content).filter_by(conversation_id=conversation_id)

        # 如果提供了 tasktype，则增加筛选条件
        if tasktype:
            query = query.filter_by(task_type=tasktype)

        # 按创建时间升序排序
        messages = query.order_by(ChatHistory.created_at.asc()).all()
        # 转换查询结果为 NamedTuple 格式
        messages_tuples = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        return messages_tuples

    except Exception as e:
        print(f"查询消息失败: {e}")
        return []

def get_or_create_conversation_history(conversation_id, tasktype,history_cache):
    # 首先检查内存中是否存在该对话历史
    if conversation_id in history_cache and history_cache[conversation_id]:
        return history_cache[conversation_id]

    # 如果内存中没有，尝试从数据库中查询该对话历史
    try:
        messages = get_messages_from_db(conversation_id, tasktype)
        # 如果查询到历史消息，则加载到内存中
        return messages or []  # 如果没有历史记录，返回空列表
    except Exception as e:
        print(f"查询数据库失败: {e}")
        return []  # 如果查询失败，则返回空列表