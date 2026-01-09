import os
from docling.document_converter import DocumentConverter, PdfFormatOption, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions

# *******************************************************************
# THAY FILE PDF CỦA BẠN Ở ĐÂY
# *******************************************************************
DOCUMENT_PATH = "113kt.pdf"
# *******************************************************************

def create_layout_only_converter():
    """Tạo DocumentConverter chỉ đọc layout PDF, không OCR."""
    print("Đang cấu hình Docling để đọc layout (không OCR)...")

    pipeline_options = PdfPipelineOptions(
        do_ocr=False,  # ❌ Không dùng OCR, chỉ lấy layout
        extract_images=True,
        extract_tables=True,
    )

    pdf_format_option = PdfFormatOption(pipeline_options=pipeline_options)

    converter = DocumentConverter(
        format_options={InputFormat.PDF: pdf_format_option}
    )
    return converter


if __name__ == "__main__":
    converter = create_layout_only_converter()
    result = converter.convert(DOCUMENT_PATH)
    doc = result.document

    print("\n=== 8 khối đầu tiên (Layout) ===")
    for i, item in enumerate(doc.texts[:8], start=1):
        prov = item.prov[0] if item.prov else None
        page_no = getattr(prov, 'page_no', 'N/A') if prov else 'N/A'
        bbox = getattr(prov, 'bbox', 'N/A') if prov else 'N/A'
        
        print(f"\nKhối {i}:")
        print(f"Trang : {page_no}")
        print(f"Text  : {item.text}")
        print(f"BBox  : {bbox}")

#.\docling-env\Scripts\activate.bat