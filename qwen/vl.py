from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from openai import OpenAI
import os
import shutil
from uuid import uuid4
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 初始化 OpenAI 客户端（对接百炼）
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

MODEL_NAME = "qwen-vl-max-latest"
app = FastAPI(title="图文问答 API")

# 对话上下文（简单内存缓存）
conversation_context: List[dict] = [
    {
        "role": "system",
        "content": [{"type": "text", "text": "You are a helpful assistant."}]
    }
]

# 图片上传文件夹（绝对路径更安全）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 静态文件挂载，URL路径/static 映射到 uploads 文件夹
app.mount("/static", StaticFiles(directory=UPLOAD_DIR), name="static")

# ---------- 接口 1：通过网络图片 URL 或纯文本 ----------
class ChatRequest(BaseModel):
    text: Optional[str] = None
    image_url: Optional[str] = None

class ChatResponse(BaseModel):
    response: str

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.text and not req.image_url:
        raise HTTPException(status_code=400, detail="至少提供文字或图片 URL")

    user_content = []
    if req.image_url:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": req.image_url}
        })
    if req.text:
        user_content.append({
            "type": "text",
            "text": req.text
        })

    conversation_context.append({
        "role": "user",
        "content": user_content
    })

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=conversation_context
        )
        assistant_msg = completion.choices[0].message
        conversation_context.append(assistant_msg.model_dump())
        return ChatResponse(response=assistant_msg.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"调用模型接口失败: {str(e)}")

# ---------- 接口 2：上传本地图片文件 ----------
@app.post("/chat_file")
async def chat_file(
    file: UploadFile = File(...),
    text: Optional[str] = Form(None)
):
    file_ext = file.filename.split(".")[-1]
    filename = f"{uuid4().hex}.{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    print(f"上传文件名: {file.filename} -> 保存路径: {file_path}")

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="文件保存失败，文件不存在")

    image_url = f"http://localhost:8000/static/{filename}"
    print(f"生成的图片 URL: {image_url}")

    user_content = [{"type": "image_url", "image_url": {"url": image_url}}]
    if text:
        user_content.append({"type": "text", "text": text})

    conversation_context.append({
        "role": "user",
        "content": user_content
    })

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=conversation_context
        )
        assistant_msg = completion.choices[0].message
        conversation_context.append(assistant_msg.model_dump())
        print("模型回复:", assistant_msg.content)
        return {"response": assistant_msg.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"调用模型接口失败: {str(e)}")

# ---------- 启动服务 ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)