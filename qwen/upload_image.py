import os
import requests
import tempfile
import logging
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any
from dotenv import load_dotenv
load_dotenv()  # 加载.env文件中的环境变量

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Image Upload Service",
    description="Upload images and generate public URLs",
    version="1.0.0"
)


def get_upload_policy(api_key: str, model_name: str) -> Dict[str, Any]:
    """获取文件上传凭证"""
    url = "https://dashscope.aliyuncs.com/api/v1/uploads"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    params = {
        "action": "getPolicy",
        "model": model_name
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()['data']
    except requests.exceptions.RequestException as e:
        logger.error(f"获取上传策略失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"获取上传策略失败: {str(e)}"
        ) from e


def upload_file_to_oss(policy_data: Dict[str, Any], file_path: str) -> str:
    """将文件上传到临时存储OSS"""
    file_name = Path(file_path).name
    key = f"{policy_data['upload_dir']}/{file_name}"

    try:
        with open(file_path, 'rb') as file:
            files = {
                'OSSAccessKeyId': (None, policy_data['oss_access_key_id']),
                'Signature': (None, policy_data['signature']),
                'policy': (None, policy_data['policy']),
                'x-oss-object-acl': (None, policy_data['x_oss_object_acl']),
                'x-oss-forbid-overwrite': (None, policy_data['x_oss_forbid_overwrite']),
                'key': (None, key),
                'success_action_status': (None, '200'),
                'file': (file_name, file)
            }

            response = requests.post(policy_data['upload_host'], files=files, timeout=30)
            response.raise_for_status()

            # 尝试获取公网访问URL
            public_host = policy_data.get('public_host')
            if public_host:
                return f"https://{public_host}/{key}"

            # 如果没有public_host，尝试从upload_host构建
            upload_host = policy_data['upload_host']
            if upload_host.startswith("https://"):
                return f"{upload_host}/{key}"

            # 默认构建方式
            return f"https://{upload_host}/{key}"

    except requests.exceptions.RequestException as e:
        logger.error(f"上传文件到OSS失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"上传文件到OSS失败: {str(e)}"
        ) from e


@app.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    """上传图片并返回公网URL接口"""
    # 1. 获取API密钥
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("API密钥未配置")
        return JSONResponse(
            status_code=500,
            content={"error": "API密钥未配置，请设置DASHSCOPE_API_KEY环境变量"}
        )

    # 2. 创建临时文件保存上传内容
    temp_file = None
    try:
        model_name = "qwen-vl-plus"
        file_suffix = Path(file.filename).suffix if file.filename else ".tmp"

        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as tmp_file:
            # 保存上传内容到临时文件
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        # 3. 获取上传策略
        policy_data = get_upload_policy(api_key, model_name)

        # 4. 上传文件到OSS并获取公网URL
        public_url = upload_file_to_oss(policy_data, tmp_file_path)

        # 5. 计算过期时间
        expire_time = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")

        # 返回结果
        return {
            "url": public_url,
            "expire": expire_time,
            "message": "文件上传成功，有效期为48小时",
            "filename": file.filename
        }

    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": str(e.detail)}
        )
    except Exception as e:
        logger.error(f"上传失败: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"上传失败: {str(e)}"}
        )
    finally:
        # 确保清理临时文件
        if tmp_file and os.path.exists(tmp_file.name):
            try:
                os.unlink(tmp_file.name)
            except Exception as e:
                logger.error(f"删除临时文件失败: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)