import pdfplumber
import fitz  # PyMuPDF
from PIL import Image
import io
import os


def extract_text_and_tables(pdf_path):
    text_list = []
    tables_list = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            print(f"\n=== 第 {page_num + 1} 页 ===")

            # 提取文本
            text = page.extract_text()
            if text:
                print("[文本]:")
                print(text[:200], '...')  # 只显示前200个字符
                text_list.append(text)

            # 提取表格
            tables = page.extract_tables()
            for table_idx, table in enumerate(tables):
                print(f"[表格 {table_idx + 1}]:")
                for row in table:
                    print(row)
                tables_list.append(table)

    return text_list, tables_list


def extract_images(pdf_path, output_folder="images"):
    os.makedirs(output_folder, exist_ok=True)
    doc = fitz.open(pdf_path)
    image_paths = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        images = page.get_images(full=True)
        print(f"\n=== 第 {page_num + 1} 页，共发现 {len(images)} 张图片 ===")

        for img_index, img in enumerate(images):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            image = Image.open(io.BytesIO(image_bytes))

            image_path = os.path.join(output_folder, f"page{page_num + 1}_img{img_index + 1}.{image_ext}")
            image.save(image_path)
            print(f"已保存图片：{image_path}")
            image_paths.append(image_path)

    return image_paths


if __name__ == "__main__":
    pdf_file = "./docs/华为年报2024.pdf"  # 请替换为你的 PDF 文件

    # Step 1 & 2: 提取文本和表格
    texts, tables = extract_text_and_tables(pdf_file)

    # Step 3: 提取图片
    images = extract_images(pdf_file)

    print("\n=== 提取结果概览 ===")
    print(f"文本段数：{len(texts)}")
    print(f"表格数：{len(tables)}")
    print(f"图片数：{len(images)}")