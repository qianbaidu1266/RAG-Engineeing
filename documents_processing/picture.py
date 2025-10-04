import cv2
import re
import json
import os
from paddleocr import PaddleOCR


def extract_invoice_info(image_path):
    """提取发票信息并返回JSON"""
    # 1. 检查文件是否存在
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"文件不存在: {image_path}")

    # 2. 读取图像并验证
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"OpenCV无法读取图像: {image_path}（可能路径错误或文件损坏）")

    # 3. 图像预处理（添加异常处理）
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    except cv2.error as e:
        raise RuntimeError(f"图像预处理失败: {str(e)}") from e

    # 4. OCR识别（使用更新后的参数）
    ocr = PaddleOCR(use_textline_orientation=True, lang="ch")  # 替换弃用参数
    result = ocr.ocr(image_path, cls=True)  # 直接传入路径，避免重复读取
    text_lines = [line[1][0] for res in result for line in res]  # 兼容新版结果结构
    full_text = "\n".join(text_lines)

    # 5. 关键字段提取（略，同原逻辑）
    # ...正则提取代码...

    return json.dumps(extracted_data, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 使用原始文件名 + 绝对路径
    abs_path = os.path.abspath("./docs/picture3.jpg")  # 确保路径无中文乱码
    print(extract_invoice_info(abs_path))