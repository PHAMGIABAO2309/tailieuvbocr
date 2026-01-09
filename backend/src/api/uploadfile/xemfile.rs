use actix_web::{get, web, Responder, HttpResponse};
use aws_sdk_s3::{ presigning::PresigningConfig};
use std::time::Duration;
use serde::Deserialize;
use crate::api::uploadfile::minio::create_minio_client;


#[derive(Deserialize)]
pub struct FileQuery {
    pub path: String,
}

#[get("/api/downloadfileminio")]
pub async fn get_download_file_minio(query: web::Query<FileQuery>) -> impl Responder {
    let client = match create_minio_client().await {
        Ok(c) => c,
        Err(e) => return HttpResponse::InternalServerError().body(format!("Lỗi kết nối MinIO: {}", e)),
    };

    let bucket_name = "luutruvanban"; // 🪣 Tên bucket của em trong MinIO
    let file_key = &query.path; // đường dẫn file trong DB

    // Tạo link tạm (presigned URL)
    let presigned_req = client
        .get_object()
        .bucket(bucket_name)
        .key(file_key)
        .presigned(PresigningConfig::expires_in(Duration::from_secs(300)).unwrap())
        .await;

    match presigned_req {
        Ok(url) => {
            let signed_url = url.uri().to_string();
            HttpResponse::Ok().json(serde_json::json!({ "url": signed_url }))
        }
        Err(e) => HttpResponse::InternalServerError().body(format!("Lỗi tạo URL: {}", e)),
    }
}


#[get("/api/xemfile")]
pub async fn get_file_from_minio(query: web::Query<FileQuery>) -> impl Responder {
    let client = match create_minio_client().await {
        Ok(c) => c,
        Err(e) => return HttpResponse::InternalServerError().body(format!("Lỗi kết nối MinIO: {}", e)),
    };

    let bucket_name = "luutruvanban";
    let file_key = &query.path;

    // 📥 Lấy object từ MinIO
    match client.get_object().bucket(bucket_name).key(file_key).send().await {
        Ok(resp) => {
            // Lấy dữ liệu bytes từ stream
            let body = resp.body.collect().await.unwrap().into_bytes();

            HttpResponse::Ok()
                .content_type("application/pdf")
                .insert_header(("Content-Disposition", "inline")) // 👁️ Hiển thị trực tiếp
                .body(body)
        }
        Err(e) => HttpResponse::InternalServerError().body(format!("Lỗi đọc file từ MinIO: {}", e)),
    }
}
