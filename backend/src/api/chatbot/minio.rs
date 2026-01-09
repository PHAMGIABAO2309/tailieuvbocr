use actix_multipart::Multipart;
use actix_web::{post, web, HttpResponse, Responder};
use futures_util::TryStreamExt as _;
use aws_sdk_s3::primitives::ByteStream;
use serde_json::json;
use std::time::Duration;

use crate::api::uploadfile::minio::create_minio_client; // dùng hàm connect đã tạo

#[post("/api/upload_miniochat")]
pub async fn upload_to_miniochat(mut payload: Multipart) -> impl Responder {
    let client = match create_minio_client().await {
        Ok(c) => c,
        Err(e) => {
            return HttpResponse::InternalServerError().json(json!({
                "status": "error",
                "message": format!("Không kết nối được MinIO: {}", e)
            }));
        }
    };

    let bucket_name = "luutruvanban";

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

        // 🟩 Upload lên MinIO
        if let Err(e) = client
            .put_object()
            .bucket(bucket_name)
            .key(&file_name)
            .body(body)
            .send()
            .await
        {
            return HttpResponse::InternalServerError().json(json!({
                "status": "error",
                "message": format!("Lỗi upload lên MinIO: {}", e)
            }));
        }

        println!("✅ Upload thành công: {}", file_name);

        // 🟦 Tạo pre-signed URL có hạn 7 ngày
        use aws_sdk_s3::presigning::PresigningConfig;
        let expires_in = Duration::from_secs(60 * 60 * 24 * 7); // 7 ngày

        let presigned_req = client
            .get_object()
            .bucket(bucket_name)
            .key(&file_name)
            .presigned(PresigningConfig::expires_in(expires_in).unwrap())
            .await;

        let presigned_url = match presigned_req {
            Ok(req) => req.uri().to_string(),
            Err(e) => {
                return HttpResponse::InternalServerError().json(json!({
                    "status": "error",
                    "message": format!("Không tạo được pre-signed URL: {}", e)
                }));
            }
        };

        return HttpResponse::Ok().json(json!({
            "status": "success",
            "file": file_name,
            "file_url": presigned_url
        }));
    }

    HttpResponse::BadRequest().json(json!({
        "status": "error",
        "message": "Không có file nào trong request"
    }))
}
