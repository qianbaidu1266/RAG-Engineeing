import os
import requests
import pandas as pd
import logging
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
API_KEY = ' '
BASE_URL = 'https://api.dify.ai'

# 配置日志系统（包含文件名和行号）
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)


def get_paginated_data(session, url_base, headers, endpoint, params=None):
    """
    获取分页数据的通用函数
    :param session: requests.Session实例
    :param url_base: 基础URL（如'http://xxx/v1'）
    :param headers: 请求头
    :param endpoint: API端点路径（如'/datasets'）
    :param params: 查询参数（如{'category': 'news'}）
    :return: 所有页面的数据列表
    """
    all_data = []
    page = 1
    while True:
        # 构建完整URL
        url = f"{url_base}/{endpoint}"
        if params:
            url += f"?{params}&page={page}&limit=100"
        else:
            url += f"?page={page}&limit=100"

        # 发送请求
        response = session.get(url, headers=headers)
        if response.status_code != 200:
            logging.error(f"分页请求失败: {url} - 状态码: {response.status_code}")
            break

        data = response.json()
        if not data.get('data'):
            logging.warning(f"第{page}页无数据: {url}")
            break

        all_data.extend(data['data'])

        # 判断是否还有下一页
        if 'total_pages' in data and page < data['total_pages']:
            page += 1
        else:
            break
    return all_data


def fetch_json(session, url, headers):
    """封装请求逻辑"""
    try:
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"请求失败: {url}")
        logging.error(f"请求头: {headers}")
        logging.error(f"异常堆栈: {traceback.format_exc()}")
        raise


def export():
    headers = {
        'Authorization': f"Bearer {API_KEY}",
        'User-Agent': 'Mozilla/5.0 (compatible; dataFetcher/1.0)'
    }

    with requests.Session() as session:
        try:
            # 获取所有数据集
            datasets = get_paginated_data(
                session,
                BASE_URL,
                headers,
                '/v1/datasets'
            )

            # 创建存储目录
            os.makedirs('document_exports', exist_ok=True)

            for dataset in datasets:
                dataset_id = dataset.get('id')
                dataset_name = dataset.get('name', '未知数据集')

                # 获取该数据集的所有文档
                documents = get_paginated_data(
                    session,
                    BASE_URL,
                    headers,
                    f'/v1/datasets/{dataset_id}/documents'
                )

                for doc in documents:
                    doc_id = doc.get('id')
                    doc_name = doc.get('name', '无标题文档')
                    doc_content = doc.get('content', '')

                    # 获取该文档的所有片段
                    segments = get_paginated_data(
                        session,
                        BASE_URL,
                        headers,
                        f'/v1/datasets/{dataset_id}/documents/{doc_id}/segments'
                    )

                    # 构建该文档的数据表
                    df = pd.DataFrame(segments, columns=['content', 'answer', 'keywords'])
                    df.insert(0, 'document_name', doc_name)
                    df.insert(0, 'dataset_name', dataset_name)
                    df.insert(0, 'raw_content', doc_content)  # 添加原始PDF文本

                    # 保存为CSV文件
                    file_path = os.path.join(
                        'document_exports',
                        f"{doc_name}_{dataset_name}_{doc_id}.csv"
                    )
                    df.to_csv(file_path, index=False)
                    logging.info(f"已导出文档: {doc_name} ({doc_id}) → {file_path}")

        except Exception as e:
            # 捕获未预见的异常
            logging.error(f"程序终止: {str(e)}")
            logging.error(f"堆栈跟踪: {traceback.format_exc()}")
            raise


if __name__ == "__main__":
    export()