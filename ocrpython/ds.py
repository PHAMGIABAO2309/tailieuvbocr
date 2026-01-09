import os
from deepseek_ocr import DeepSeekOCR
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PIL import Image

# ===== CONFIG =====
MODEL_PATH = "D:/models/DeepSeek-OCR"   # đường dẫn model bạn đã tải
INPUT_PATH = "D:/images"                # 1 file ảnh hoặc thư mục ảnh
OUTPUT_PDF = "scan.pdf" # đường dẫn PDF output
# ==================

# Load model DeepSeek-OCR
print("Đang load model DeepSeek-OCR...")
ocr = DeepSeekOCR(model_path=MODEL_PATH)

# Chuẩn bị PDF
os.makedirs(os.path.dirname(OUTPUT_PDF), exist_ok=True)
pdf = canvas.Canvas(OUTPUT_PDF, pagesize=A4)

def write_text_to_pdf(pdf, text):
    pdf.setFont("Helvetica", 10)
    y = 800
    for line in text.split("\n"):
        pdf.drawString(40, y, line)
        y -= 15
        if y < 40:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = 800

def ocr_file(img_path):
    print(f"OCR: {img_path}")
    result = ocr.run(img_path)
    return result

# Xử lý nếu là 1 file ảnh
if os.path.isfile(INPUT_PATH):
    text = ocr_file(INPUT_PATH)
    write_text_to_pdf(pdf, text)

# Xử lý folder ảnh
else:
    files = sorted(os.listdir(INPUT_PATH))
    for f in files:
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
            full_path = os.path.join(INPUT_PATH, f)
            text = ocr_file(full_path)
            write_text_to_pdf(pdf, f"[FILE: {f}]\n{text}\n\n")

# Lưu PDF
pdf.save()
print("Xuất PDF thành công:", OUTPUT_PDF)
