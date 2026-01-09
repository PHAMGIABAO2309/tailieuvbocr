import re
import json
import http.server
import socketserver
import threading
import webbrowser
from typing import List, Dict, Tuple, Optional

# =========================
# 1. HÀM CHUẨN HÓA CHỮ VIỆT
# =========================
def normalize_vietnamese(text: str) -> str:
    """Chuẩn hóa tiếng Việt: chuyển về chữ hoa và xử lý các ký tự đặc biệt"""
    if not text:
        return text
    
    # Chuyển thành chữ hoa
    text = text.upper()
    
    # Thay thế các ký tự đặc biệt từ OCR
    replacements = {
        'UỶ': 'ỦY',  # Sửa dấu hỏi thành dấu ngã
        'ỦY': 'ỦY',  # Giữ nguyên nếu đã đúng
        'Ỹ': 'Ỷ',    # Các ký tự khác
        'Ỷ': 'Ỷ',
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    return text


# =========================
# 2. PARSE BLOCKS FROM OCR TEXT
# =========================
def parse_ocr_blocks(raw_text: str) -> List[Dict]:
    """Parse OCR blocks from text output"""
    blocks = []
    
    # Tìm tất cả các blocks với bounding box và text
    pattern = re.compile(
        r'<\|ref\|>.*?<\|/ref\|><\|det\|>\[\[(\d+\.?\d*),\s*(\d+\.?\d*),\s*(\d+\.?\d*),\s*(\d+\.?\d*)\]\]<\|/det\|>\n(.*?)(?=\n<\|ref\|>|\n===============|\Z)',
        re.DOTALL
    )
    
    for match in pattern.finditer(raw_text):
        x1, y1, x2, y2 = map(float, match.groups()[:4])
        text = match.group(5).strip()
        
        # Xử lý text có thể có nhiều dòng
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        for line in lines:
            # Loại bỏ ký tự đặc biệt # ở đầu dòng
            line = re.sub(r'^#+\s*', '', line)
            blocks.append({
                'text': line,
                'box': [int(float(x1)), int(float(y1)), int(float(x2)), int(float(y2))],
                'normalized_text': normalize_vietnamese(line)  # Thêm normalized text
            })
    
    # Ước tính kích thước ảnh từ các bounding boxes
    if blocks:
        all_x2 = [b['box'][2] for b in blocks]
        all_y2 = [b['box'][3] for b in blocks]
        img_w = max(all_x2) if all_x2 else 1000
        img_h = max(all_y2) if all_y2 else 1000
    else:
        img_w, img_h = 1000, 1000
    
    return blocks, img_w, img_h


# =========================
# 3. BOX UTILITIES
# =========================
def get_center(box: List[int], img_w: int, img_h: int) -> Tuple[float, float]:
    """Get normalized center coordinates of a box"""
    x0, y0, x1, y1 = box
    return ((x0 + x1) / 2) / img_w, ((y0 + y1) / 2) / img_h


def is_in_left_half(box: List[int], img_w: int, threshold: float = 0.5) -> bool:
    """Check if box is in left half of image"""
    x0, _, x1, _ = box
    center_x = (x0 + x1) / 2
    return center_x < img_w * threshold


def is_in_right_half(box: List[int], img_w: int, threshold: float = 0.5) -> bool:
    """Check if box is in right half of image"""
    x0, _, x1, _ = box
    center_x = (x0 + x1) / 2
    return center_x > img_w * threshold


# =========================
# 4. EXTRACTION FUNCTIONS
# =========================
def clean_combined_text(text: str, patterns_to_remove: List[str] = None) -> str:
    """Xử lý text bị gộp nhiều thông tin"""
    if patterns_to_remove is None:
        patterns_to_remove = []
    
    # Loại bỏ các dấu # và khoảng trắng thừa
    text = re.sub(r'#+\s*', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Tách thông tin nếu text chứa cả cơ quan và số hiệu
    # Pattern cho cơ quan
    org_patterns = [
        r'(ỦY BAN NHÂN DÂN|BỘ|UBND|SỞ)[^S]*',
        r'^[^S]*?(?=S[ỐO]\s*[:])',
    ]
    
    for pattern in org_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            org_part = match.group(0).strip()
            # Nếu phần cơ quan hợp lý (có độ dài nhất định)
            if len(org_part) > 5:
                return org_part
    
    return text


def extract_co_quan_ban_hanh(blocks: List[Dict], img_w: int, img_h: int) -> str:
    """Extract issuing organization"""
    candidates = []
    
    # Tìm các block có chứa từ khóa cơ quan (sử dụng normalized_text)
    org_keywords = ['ỦY BAN', 'BỘ', 'SỞ', 'UBND', 'QUỐC PHÒNG', 'CHÍNH PHỦ']
    
    for block in blocks:
        # Sử dụng normalized_text đã được chuẩn hóa
        text_normalized = block['normalized_text']
        
        # Kiểm tra nếu là cơ quan ban hành
        if any(keyword in text_normalized for keyword in org_keywords):
            # Kiểm tra vị trí (thường ở góc trên bên trái)
            _, y_center = get_center(block['box'], img_w, img_h)
            x_center, _ = get_center(block['box'], img_w, img_h)
            
            # Ưu tiên các block ở phần trên bên trái của văn bản
            if y_center < 0.4 and x_center < 0.6:  # Nới rộng ngưỡng
                # Xử lý text bị gộp
                clean_text = clean_combined_text(block['text'])
                candidates.append((y_center, clean_text))
    
    if candidates:
        # Chọn cái ở trên cùng
        candidates.sort(key=lambda x: x[0])
        best_candidate = candidates[0][1]
        
        # Loại bỏ phần số hiệu nếu bị gộp
        # Nếu có chứa "Số:" thì tách lấy phần trước
        if 'SỐ:' in best_candidate.upper() or 'SO:' in best_candidate.upper():
            parts = re.split(r'S[ỐO]\s*[:]', best_candidate, flags=re.IGNORECASE)
            if parts and parts[0].strip():
                best_candidate = parts[0].strip()
        
        return best_candidate
    
    return ""


def extract_so_ky_hieu(blocks: List[Dict], img_w: int, img_h: int) -> str:
    """Extract document number"""
    # Các pattern cho số ký hiệu (sử dụng normalized_text)
    patterns = [
        r'S[ỐO]\s*[:\-]\s*[^,\n]{0,50}',  # Số: ... (giới hạn độ dài)
        r'\b\d+[/\-]\w+[/\-]?\w*\b',       # 145/UBND hoặc 145/UBND-TCDNC
    ]
    
    found_blocks = []
    
    for block in blocks:
        text = block['text']
        text_normalized = block['normalized_text']
        
        # Kiểm tra vị trí (thường ở góc trên bên trái, dưới cơ quan ban hành)
        _, y_center = get_center(block['box'], img_w, img_h)
        x_center, _ = get_center(block['box'], img_w, img_h)
        
        # Số ký hiệu thường ở phần trên (y_center < 0.4) và bên trái (x_center < 0.6)
        if not (0.05 < y_center < 0.5 and x_center < 0.7):
            continue
        
        # Kiểm tra các pattern (sử dụng normalized_text)
        for pattern in patterns:
            matches = re.findall(pattern, text_normalized, re.IGNORECASE)
            for match in matches:
                if match and len(match.strip()) > 3:  # Loại bỏ kết quả quá ngắn
                    found_blocks.append((y_center, match.strip()))
        
        # Nếu text ngắn và có chứa "/" hoặc "Số:" (sử dụng text gốc)
        if '/' in text or 'Số:' in text or 'So:' in text:
            found_blocks.append((y_center, text.strip()))
    
    if not found_blocks:
        return ""
    
    # Chọn block ở vị trí thấp nhất trong phạm vi cho phép
    found_blocks.sort(key=lambda x: x[0])
    
    # Lấy kết quả đầu tiên và làm sạch
    result = found_blocks[0][1]
    
    # Loại bỏ phần trích yếu nếu bị gộp
    if 'V/V' in result.upper() or 'VỀ VIỆC' in result.upper():
        parts = re.split(r'V[\/v]|Về việc', result, flags=re.IGNORECASE)
        if parts and parts[0].strip():
            result = parts[0].strip()
    
    # Loại bỏ phần cơ quan nếu bị gộp
    org_keywords = ['ỦY BAN', 'BỘ', 'UBND']
    for keyword in org_keywords:
        if keyword in normalize_vietnamese(result):
            # Tìm vị trí của "Số:" sau keyword
            so_pattern = r'S[ỐO]\s*[:\-]'
            so_match = re.search(so_pattern, normalize_vietnamese(result), re.IGNORECASE)
            if so_match:
                result = result[so_match.start():].strip()
    
    return result


def extract_ngay_ban_hanh(blocks: List[Dict], img_w: int, img_h: int) -> str:
    """Extract issue date"""
    date_patterns = [
        r'ngày\s+\d+\s+tháng\s+\d+\s+năm\s+\d{4}',
        r'ngày\s+\d+[/\-]\d+[/\-]\d{4}',
        r'\d+\s+tháng\s+\d+\s+năm\s+\d{4}',
        r'\d{1,2}[/\-]\d{1,2}[/\-]\d{4}',
    ]
    
    candidates = []
    
    for block in blocks:
        text = block['text']
        text_lower = text.lower()
        
        # Kiểm tra vị trí (thường ở góc trên bên phải)
        x_center, y_center = get_center(block['box'], img_w, img_h)
        
        # Nới rộng điều kiện: bên phải và ở phần trên của văn bản
        if not (is_in_right_half(block['box'], img_w, 0.4) and y_center < 0.4):
            continue
        
        # Kiểm tra các pattern ngày tháng
        for pattern in date_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                date_text = match.group(0)
                # Kiểm tra xem có phải là ngày tháng hợp lệ không
                if any(char.isdigit() for char in date_text):
                    candidates.append((y_center, date_text))
        
        # Kiểm tra trực tiếp nếu có từ "ngày"
        if 'ngày' in text_lower:
            # Tìm phần có chứa số sau từ "ngày"
            date_match = re.search(r'ngày[^\d]*(\d+[^\d]*\d+[^\d]*\d{4})', text_lower)
            if date_match:
                full_date = f"ngày {date_match.group(1)}"
                candidates.append((y_center, full_date))
    
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
    
    return ""


def extract_ten_van_ban(blocks: List[Dict], so_ky_hieu: str = "") -> str:
    """Extract document type/name"""
    # Loại bỏ công văn khỏi danh sách văn bản chính thức
    doc_types = {
        'QUYẾT ĐỊNH': 'QUYẾT ĐỊNH',
        'THÔNG BÁO': 'THÔNG BÁO', 
        'CHỈ THỊ': 'CHỈ THỊ',
        'BÁO CÁO': 'BÁO CÁO',
        'TỜ TRÌNH': 'TỜ TRÌNH',
        'KẾ HOẠCH': 'KẾ HOẠCH',
        'NGHỊ QUYẾT': 'NGHỊ QUYẾT'
    }
    
    candidates = []
    
    for block in blocks:
        text = block['text'].strip()
        text_normalized = block['normalized_text']
        
        # Bỏ qua nếu là số ký hiệu
        if so_ky_hieu and (so_ky_hieu in text or so_ky_hieu in text_normalized):
            continue
        
        # Bỏ qua nếu là phần ngày tháng
        if 'NGÀY' in text_normalized and any(char.isdigit() for char in text):
            continue
        
        # Bỏ qua nếu là cơ quan ban hành
        org_keywords = ['ỦY BAN', 'BỘ', 'UBND', 'SỞ']
        if any(keyword in text_normalized for keyword in org_keywords):
            continue
        
        # Bỏ qua nếu text quá dài (tên văn bản thường ngắn)
        if len(text) > 50:
            continue
        
        # Tìm tên văn bản chính thức
        for doc_type in doc_types:
            # Kiểm tra nếu text chứa tên văn bản
            if doc_type in text_normalized:
                # Kiểm tra độ dài hợp lý
                if len(text) < 30:
                    candidates.append((len(text), doc_type))
    
    if candidates:
        # Chọn cái ngắn nhất (tên văn bản thường ngắn)
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
    
    # Mặc định là CÔNG VĂN nếu không tìm thấy văn bản chính thức
    return "CÔNG VĂN"


def extract_trich_yeu(blocks: List[Dict], so_ky_hieu: str, ten_van_ban: str, img_w: int, img_h: int) -> str:
    """Extract document summary with improved logic from trichyeujson.py"""
    
    # Sắp xếp blocks theo vị trí từ trên xuống dưới
    sorted_blocks = sorted(blocks, key=lambda b: b['box'][1])
    
    # Xác định loại văn bản
    is_cong_van = ten_van_ban.upper() == "CÔNG VĂN"
    
    # TRƯỜNG HỢP 1: VĂN BẢN CÓ TÊN (THÔNG BÁO, QUYẾT ĐỊNH, v.v.)
    if not is_cong_van:
        # Tìm dòng chứa tên văn bản
        ten_van_ban_index = -1
        for i, block in enumerate(sorted_blocks):
            if normalize_vietnamese(block['text'].strip()) == ten_van_ban.upper():
                ten_van_ban_index = i
                break
        
        # Nếu tìm thấy tên văn bản, lấy dòng ngay sau đó
        if ten_van_ban_index != -1 and ten_van_ban_index + 1 < len(sorted_blocks):
            next_block = sorted_blocks[ten_van_ban_index + 1]
            next_text = next_block['text'].strip()
            
            # Kiểm tra đây có phải là trích yếu hợp lý không
            # Trích yếu không nên quá ngắn hoặc quá dài, và không chứa các từ khóa của phần khác
            if (10 < len(next_text) < 500 and 
                not any(keyword in normalize_vietnamese(next_text) for keyword in ['CĂN CỨ', 'THEO', 'KÍNH GỬI', 'SỐ:']) and
                'NGÀY' not in normalize_vietnamese(next_text)):
                return next_text
            
            # Nếu dòng tiếp theo không hợp lý, tìm dòng đầu tiên có độ dài hợp lý sau tên văn bản
            for i in range(ten_van_ban_index + 1, min(ten_van_ban_index + 5, len(sorted_blocks))):
                block_text = sorted_blocks[i]['text'].strip()
                if 20 < len(block_text) < 500:
                    # Kiểm tra không phải là các phần thông thường của văn bản
                    if not any(keyword in normalize_vietnamese(block_text) for keyword in ['CĂN CỨ', 'THEO', 'SỐ:', 'NGÀY']):
                        return block_text
    
    # TRƯỜNG HỢP 2: CÔNG VĂN
    else:
        # Tìm trong tất cả các blocks có chứa "V/v" hoặc "Về việc"
        for block in sorted_blocks:
            text = block['text'].strip()
            
            # Tìm "V/v" hoặc "Về việc" trong text
            vv_pattern = r'(V/v|Về việc|VỀ VIỆC)'
            match = re.search(vv_pattern, text, re.IGNORECASE)
            
            if match:
                # Lấy phần từ "V/v" hoặc "Về việc" trở đi
                start_pos = match.start()
                trich_yeu_text = text[start_pos:]
                
                # QUAN TRỌNG: KHÔNG tách bằng dấu phân cách nữa
                # Chỉ loại bỏ ký tự # và khoảng trắng thừa
                trich_yeu_text = re.sub(r'#+\s*', '', trich_yeu_text)
                trich_yeu_text = re.sub(r'\s+', ' ', trich_yeu_text)
                
                # Lấy TOÀN BỘ nội dung, không cắt
                # (vì trong data của bạn, trích yếu chỉ nằm trên 1 dòng)
                if '\n' in trich_yeu_text:
                    trich_yeu_text = trich_yeu_text.split('\n')[0].strip()
                
                # Kiểm tra độ dài hợp lý - mở rộng giới hạn lên 1000 ký tự
                if 10 < len(trich_yeu_text) < 1000:
                    return trich_yeu_text
        
        # Nếu không tìm thấy bằng pattern, tìm dòng bắt đầu bằng "V/v"
        for block in sorted_blocks:
            text = block['text'].strip()
            if text.upper().startswith('V/V') or text.startswith('V/v'):
                # Làm sạch text
                clean_text = re.sub(r'#+\s*', '', text)
                clean_text = re.sub(r'\s+', ' ', clean_text)
                
                if 10 < len(clean_text) < 1000:
                    return clean_text
    
    # TRƯỜNG HỢP 3: FALLBACK - tìm dòng có nội dung hợp lý nhất
    for block in sorted_blocks:
        text = block['text'].strip()
        
        # Bỏ qua các dòng header
        header_keywords = ['ỦY BAN', 'BỘ', 'UBND', 'SỞ', 'CỘNG HÒA', 'KÍNH GỬI', 'SỐ:', 'NGÀY']
        if any(keyword in normalize_vietnamese(text) for keyword in header_keywords):
            continue
        
        # Bỏ qua nếu là số ký hiệu
        if so_ky_hieu and so_ky_hieu in text:
            continue
        
        # Bỏ qua nếu là tên văn bản
        if ten_van_ban and ten_van_ban.upper() in normalize_vietnamese(text):
            continue
        
        # Kiểm tra độ dài hợp lý cho trích yếu
        if 20 < len(text) < 300:
            # Kiểm tra vị trí (nên ở phần trên của văn bản)
            _, y_center = get_center(block['box'], img_w, img_h)
            if 0.15 < y_center < 0.4:  # Phần giữa trên của văn bản
                # Làm sạch text
                clean_text = re.sub(r'#+\s*', '', text)
                clean_text = re.sub(r'\s+', ' ', clean_text)
                return clean_text
    
    return ""


# =========================
# 5. MAIN EXTRACTION FUNCTION
# =========================
def extract_document_info(file_content: str) -> Dict:
    """Main function to extract all document fields"""
    # Parse blocks từ OCR text
    blocks, img_w, img_h = parse_ocr_blocks(file_content)
    
    if not blocks:
        return {
            'co_quan_ban_hanh': '',
            'so_ky_hieu': '',
            'ngay_ban_hanh': '',
            'ten_van_ban': 'CÔNG VĂN',
            'trich_yeu': ''
        }
    
    # Trích xuất các trường theo thứ tự ưu tiên
    so_ky_hieu = extract_so_ky_hieu(blocks, img_w, img_h)
    co_quan = extract_co_quan_ban_hanh(blocks, img_w, img_h)
    ngay_ban_hanh = extract_ngay_ban_hanh(blocks, img_w, img_h)
    ten_van_ban = extract_ten_van_ban(blocks, so_ky_hieu)
    
    # Trích yếu cần thông tin về tên văn bản để xác định vị trí chính xác
    trich_yeu = extract_trich_yeu(blocks, so_ky_hieu, ten_van_ban, img_w, img_h)
    
    # THÊM: Xử lý đặc biệt nếu trích yếu bị thiếu
    if not trich_yeu or len(trich_yeu) < 20:
        # Tìm trực tiếp trong raw content
        lines = file_content.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if 'V/v' in line or 'Về việc' in line:
                # Lấy dòng này và các dòng tiếp theo nếu cần
                trich_candidate = line
                # Thử lấy thêm dòng tiếp theo nếu dòng hiện tại quá ngắn
                if len(trich_candidate) < 30 and i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line.startswith('<|'):
                        trich_candidate += ' ' + next_line
                
                # Làm sạch
                trich_candidate = re.sub(r'#+\s*', '', trich_candidate)
                trich_candidate = re.sub(r'\s+', ' ', trich_candidate)
                trich_candidate = trich_candidate.strip()
                
                if trich_candidate and len(trich_candidate) > 10:
                    trich_yeu = trich_candidate
                    break
    
    # Làm sạch kết quả lần cuối
    def clean_final_text(text):
        if not text:
            return text
        # Loại bỏ các ký tự thừa và chuẩn hóa khoảng trắng
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'#+\s*', '', text)  # Loại bỏ dấu #
        text = re.sub(r'^[^A-Za-zÀ-ỹ]*', '', text)  # Loại bỏ ký tự không phải chữ ở đầu
        text = text.strip()
        return text
    
    # Xử lý đặc biệt cho trường hợp text bị gộp
    if so_ky_hieu and co_quan and so_ky_hieu in co_quan:
        # Tách số hiệu ra khỏi cơ quan
        parts = co_quan.split(so_ky_hieu)
        if parts and parts[0].strip():
            co_quan = parts[0].strip()
    
    result = {
        'co_quan_ban_hanh': clean_final_text(co_quan),
        'so_ky_hieu': clean_final_text(so_ky_hieu),
        'ngay_ban_hanh': clean_final_text(ngay_ban_hanh),
        'ten_van_ban': clean_final_text(ten_van_ban),
        'trich_yeu': clean_final_text(trich_yeu)
    }
    
    return result


# =========================
# 6. PROCESS MULTIPLE FILES
# =========================
def process_ocr_files(file_paths: List[str], output_file: str = "output.json"):
    """Process multiple OCR files and save results"""
    all_results = {}
    
    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Trích xuất thông tin
            result = extract_document_info(content)
            all_results[file_path] = result
            
            print(f"✓ Đã xử lý: {file_path}")
            print(f"  - Cơ quan: {result['co_quan_ban_hanh'][:50]}...")
            print(f"  - Số ký hiệu: {result['so_ky_hieu']}")
            print(f"  - Ngày ban hành: {result['ngay_ban_hanh']}")
            print(f"  - Tên văn bản: {result['ten_van_ban']}")
            print(f"  - Trích yếu: {result['trich_yeu'][:60]}...")
            print()
            
        except Exception as e:
            print(f"✗ Lỗi khi xử lý {file_path}: {str(e)}")
    
    # Lưu kết quả
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print(f"✔ Đã lưu kết quả vào {output_file}")
    return all_results


# =========================
# 7. RUN WITH SINGLE FILE + EXPORT JSON + SERVE LOCALHOST
# =========================
def run_single_file(input_file="text.txt", output_file="result.json"):
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            content = f.read()

        result = extract_document_info(content)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"✔ Đã xử lý {input_file}")
        print(f"✔ Đã lưu kết quả vào {output_file}")

        return output_file

    except Exception as e:
        print(f"✗ Lỗi: {e}")
        return None


def start_localhost(port=8000):
    handler = http.server.SimpleHTTPRequestHandler
    httpd = socketserver.TCPServer(("", port), handler)

    print(f"🌐 Đang chạy localhost tại: http://localhost:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    # Có thể chạy nhiều file hoặc một file đơn lẻ
    INPUT_FILE = "text.txt"
    OUTPUT_FILE = "result.json"

    # Xử lý file đơn lẻ
    output = run_single_file(INPUT_FILE, OUTPUT_FILE)

    if output:
        # chạy server trong thread riêng
        server_thread = threading.Thread(target=start_localhost, daemon=True)
        server_thread.start()

        # tự mở trình duyệt xem file json
        webbrowser.open(f"http://localhost:8000/{OUTPUT_FILE}")

        input("Nhấn Enter để dừng server...")
    
    # Hoặc xử lý nhiều file:
    # file_list = ["text.txt", "resultsvb1.txt", "resultsvb2.txt", "resultscv1.txt", "resultscv2.txt"]
    # process_ocr_files(file_list, "output_all.json")