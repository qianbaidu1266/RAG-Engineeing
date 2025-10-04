
from fastapi import FastAPI
from db import query_mysql

app = FastAPI()

@app.get("/query")
async def get_users():
    sql = "SELECT * FROM sys_user"
    results = await query_mysql(sql)
    return {"data": results}


# 支持直接用 python main.py 启动
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
