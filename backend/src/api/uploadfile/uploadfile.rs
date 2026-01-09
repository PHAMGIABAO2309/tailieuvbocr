use actix_multipart::Multipart;
use actix_web::{post, web, HttpResponse, Responder};
use futures_util::TryStreamExt as _;
use aws_sdk_s3::primitives::ByteStream;
use serde_json::json;

use crate::api::uploadfile::minio::create_minio_client; // dùng lại hàm connect sẵn có

#[post("/api/upload_minio")]
pub async fn upload_to_minio(mut payload: Multipart) -> impl Responder {
    let client = match create_minio_client().await {
        Ok(c) => c,
        Err(e) => {
            return HttpResponse::InternalServerError().json(json!({
                "status": "error",
                "message": format!("Không kết nối được MinIO: {}", e)
            }));
        }
    };

    let bucket_name = "luutruvanban"; // ⚠️ nhớ tạo sẵn bucket này trong MinIO

    // Duyệt từng phần trong multipart
    while let Ok(Some(mut field)) = payload.try_next().await {
        let content_disposition = field.content_disposition();
        let file_name = content_disposition
            .get_filename()
            .map(|f| f.to_string())
            .unwrap_or_else(|| "unknown_file".to_string());

        println!("📄 Upload file: {}", file_name);

        let mut file_bytes = web::BytesMut::new();
        while let Ok(Some(chunk)) = field.try_next().await {
            file_bytes.extend_from_slice(&chunk);
        }

        let body = ByteStream::from(file_bytes.to_vec());

        // Gửi lên MinIO
        let res = client
            .put_object()
            .bucket(bucket_name)
            .key(&file_name)
            .body(body)
            .send()
            .await;

        match res {
            Ok(_) => {
                println!("✅ Upload thành công: {}", file_name);
                return HttpResponse::Ok().json(json!({
                    "status": "success",
                    "file": file_name,
                    "url": format!("http://127.0.0.1:9000/{}/{}", bucket_name, file_name)
                }));
            }
            Err(e) => {
                return HttpResponse::InternalServerError().json(json!({
                    "status": "error",
                    "message": format!("Lỗi upload lên MinIO: {}", e)
                }));
            }
        }
    }

    HttpResponse::BadRequest().json(json!({
        "status": "error",
        "message": "Không có file nào trong request"
    }))
}
