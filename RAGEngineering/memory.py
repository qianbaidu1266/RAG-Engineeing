import os
from dotenv import load_dotenv
import aiomysql
import aioredis
import json

load_dotenv()

class MemoryManager:
    def __init__(self):
        self.redis = None
        self.mysql_pool = None

    async def init(self):
        # Redis
        redis_url = os.getenv("REDIS_URL")
        self.redis = await aioredis.from_url(
            redis_url, encoding="utf-8", decode_responses=True
        )
        # MySQL
        self.mysql_pool = await aiomysql.create_pool(
            host=os.getenv("MYSQL_HOST"),
            port=int(os.getenv("MYSQL_PORT")),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            db=os.getenv("MYSQL_DB"),
            autocommit=True
        )

    async def save_to_redis(self, conversation_id, messages):
        await self.redis.set(f"conv:{conversation_id}", json.dumps(messages))

    async def load_from_redis(self, conversation_id):
        data = await self.redis.get(f"conv:{conversation_id}")
        return json.loads(data) if data else []

    async def save_to_mysql(self, conversation_id, messages):
        async with self.mysql_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "REPLACE INTO conversations (conversation_id, messages) VALUES (%s, %s)",
                    (conversation_id, json.dumps(messages))
                )

    async def load_from_mysql(self, conversation_id):
        async with self.mysql_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT messages FROM conversations WHERE conversation_id=%s",
                    (conversation_id,)
                )
                row = await cur.fetchone()
                return json.loads(row[0]) if row else []

    async def close(self):
        self.mysql_pool.close()
        await self.mysql_pool.wait_closed()
        await self.redis.close()
