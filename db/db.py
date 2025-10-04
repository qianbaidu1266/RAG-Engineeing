import pymysql
import aiomysql
from typing import List, Dict

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'password',
    'db': 'vueadmin',
    'port': 3306,
    'charset': 'utf8mb4',
    "autocommit": True
}

# 获取连接池（FastAPI 应该全局复用一个池）
async def get_pool():
    return await aiomysql.create_pool(minsize=1, maxsize=5, **DB_CONFIG)

# 通用查询函数
async def query_mysql(sql: str, params: tuple = ()) -> List[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, params)
            result = await cur.fetchall()
    pool.close()
    await pool.wait_closed()
    return result