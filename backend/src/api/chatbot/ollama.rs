use actix_web::{post, web, HttpResponse, Responder};
use serde::{Deserialize, Serialize};
use reqwest::Client;
use serde_json::Value;
use tempfile::tempdir;
use std::{fs, io::Write, process::Command, path::PathBuf};
use std::sync::{Arc, Mutex};
pub type SharedMemory = Arc<Mutex<Option<String>>>; 

#[derive(Deserialize)]
struct ChatRequest {
    file_url: String, // link pre-signed từ MinIO
}

#[derive(Serialize)]
struct ChatResponse {
    summary: String,
}

#[derive(Deserialize)]
struct AskRequest {
    message: String,
}



#[post("/chatbot/tomtat")]
async fn chatbot_tomtat(
    req: web::Json<ChatRequest>,
    memory: web::Data<SharedMemory>, // 🟢 thêm vào đây
) -> impl Responder {
    let client = Client::new();

    // 1️⃣ Tải file PDF từ MinIO (pre-signed URL)
    let resp = client.get(&req.file_url).send().await;
    let bytes = match resp {
        Ok(r) => match r.bytes().await {
            Ok(b) => b,
            Err(_) => return HttpResponse::BadRequest().body("Không thể tải file từ MinIO"),
        },
        Err(_) => return HttpResponse::BadRequest().body("URL không hợp lệ"),
    };

    // 2️⃣ Tạo thư mục tạm chứa file
    let dir = tempdir().expect("Không tạo được thư mục tạm");
    let pdf_path = dir.path().join("input.pdf");
    let mut pdf_file = fs::File::create(&pdf_path).expect("Không ghi được file PDF");
    pdf_file.write_all(&bytes).expect("Không ghi được nội dung PDF");

    // 3️⃣ Chuyển PDF → ảnh PNG trong cùng thư mục
    let image_base = dir.path().join("page");
    let image_base_str = image_base.to_str().unwrap();

    let output = Command::new("D:\\poppler-25.07.0\\Library\\bin\\pdftoppm.exe")
        .arg("-r")
        .arg("300")
        .arg(&pdf_path)
        .arg(image_base_str)
        .arg("-png")
        .output()
        .expect("Không chạy được pdftoppm");

    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        eprintln!("❌ Lỗi pdftoppm: {}", err);
        return HttpResponse::InternalServerError()
            .body(format!("❌ pdftoppm lỗi:\n{}", err));
    }

    // 4️⃣ OCR từng ảnh
    let mut ocr_text = String::new();
    for entry in fs::read_dir(dir.path()).unwrap() {
        if let Ok(entry) = entry {
            let path: PathBuf = entry.path();
            if path.extension().map(|e| e == "png").unwrap_or(false) {
                eprintln!("🔍 OCR ảnh: {}", path.display());
                let ocr_output = Command::new("tesseract")
                    .arg(&path)
                    .arg("stdout")
                    .arg("-l")
                    .arg("vie") 
                    .output();

                match ocr_output {
    Ok(result) => {
        let text = String::from_utf8_lossy(&result.stdout);
        eprintln!("🧪 OCR TEXT ({}):\n{}", path.display(), text);
        ocr_text.push_str(&text);
    }
                    Err(e) => {
                        eprintln!("⚠️ Lỗi OCR ảnh {}: {}", path.display(), e);
                    }
                }
            }
        }
    }

    if ocr_text.trim().is_empty() {
        return HttpResponse::Ok().json(ChatResponse {
            summary: "⚠️ OCR thất bại hoặc PDF trống.".to_string(),
        });
    }

   
    // 5️⃣ Gọi Ollama để tóm tắt lần 1
    let prompt = format!("Hãy tóm tắt ngắn gọn nội dung sau bằng tiếng Việt:\n\n{}", ocr_text);
    let res = client
        .post("http://localhost:11434/api/generate")
        .json(&serde_json::json!({
            "model": "llama3:8b",
            "prompt": prompt,
            "stream": false
        }))
        .send()
        .await;

    let summary1 = match res {
        Ok(mut response) => {
            let result = response.text().await.unwrap_or_default();
            if let Ok(json_line) = serde_json::from_str::<Value>(&result) {
                json_line["response"].as_str().unwrap_or("").to_string()
            } else {
                result
            }
        }
        Err(err) => return HttpResponse::InternalServerError()
            .body(format!("Lỗi khi gọi Ollama lần 1: {}", err)),
    };

    // 6️⃣ Gọi Ollama lần 2 để tóm tắt lại ngắn gọn hơn nữa
    let refine_prompt = format!(
        "Hãy tóm tắt lại đoạn sau cho NGẮN GỌN hơn nữa, giữ ý chính, bằng tiếng Việt:\n\n{}",
        summary1
    );

    let res2 = client
        .post("http://localhost:11434/api/generate")
        .json(&serde_json::json!({
            "model": "llama3:8b",
            "prompt": refine_prompt,
            "stream": false
        }))
        .send()
        .await;

     match res2 {
        Ok(mut response) => {
            let result = response.text().await.unwrap_or_default();
            let summary2 = if let Ok(json_line) = serde_json::from_str::<Value>(&result) {
                json_line["response"].as_str().unwrap_or("").to_string()
            } else {
                result
            };

            // 🟢 Lưu đoạn tóm tắt vào SharedMemory
            {
                let mut mem = memory.lock().unwrap();
                *mem = Some(summary2.clone());
            }

            HttpResponse::Ok().json(ChatResponse { summary: summary2 })
        }
        Err(err) => HttpResponse::Ok().json(ChatResponse {
            summary: format!("(Đã tóm tắt lần 1, nhưng lỗi khi rút gọn thêm: {})\n{}", err, summary1),
        }),
    }
}





#[post("/chatbot/hoi")]
pub async fn chatbot_hoi(
    req: web::Json<AskRequest>,
    memory: web::Data<SharedMemory>,
) -> impl Responder {
    let client = Client::new();

    // 🔹 Dùng bộ nhớ làm ngữ cảnh
    let context = {
        let mem = memory.lock().unwrap();
        if let Some(prev) = &*mem {
            format!("Đoạn văn trước đó:\n{}\n\nCâu hỏi mới: {}", prev, req.message)
        } else {
            req.message.clone()
        }
    };

    let prompt = format!(
        "Bạn là AI trả lời NGẮN GỌN, bằng tiếng Việt. \
        Hãy trả lời câu sau dựa trên ngữ cảnh nếu có:\n\n{}",
        context
    );

    let res = client
        .post("http://localhost:11434/api/generate")
        .json(&serde_json::json!({
            "model": "llama3:8b",
            "prompt": prompt,
            "stream": false
        }))
        .send()
        .await;

    match res {
        Ok(response) => {
            let result = response.text().await.unwrap_or_default();

            let reply = if let Ok(json_line) = serde_json::from_str::<Value>(&result) {
                json_line["response"].as_str().unwrap_or("").to_string()
            } else {
                result
            };

            // 🔹 Cập nhật bộ nhớ
            let mut mem = memory.lock().unwrap();
            *mem = Some(reply.clone());

            HttpResponse::Ok().json(ChatResponse { summary: reply })
        }
        Err(err) => HttpResponse::InternalServerError()
            .body(format!("Lỗi khi gọi Ollama: {}", err)),
    }
}