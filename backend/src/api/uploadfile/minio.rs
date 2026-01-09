use actix_web::{get, Responder, HttpResponse};
use aws_config::{Region, BehaviorVersion};
use aws_sdk_s3::{config::Builder, Client};
use aws_credential_types::Credentials;
use serde_json::json;
use std::error::Error;

pub async fn create_minio_client() -> Result<Client, Box<dyn Error>> {
    // 🧱 Thông tin MinIO
    let endpoint_url = "http://127.0.0.1:9000";
    let access_key = "minioadmin";
    let secret_key = "minioadmin";

    // 🔑 Credentials
    let creds = Credentials::new(
        access_key,
        secret_key,
        None,
        None,
        "static",
    );

    // 🌍 Region (MinIO không cần, nhưng SDK bắt buộc có)
    let region = Region::new("us-east-1");

    // 🧩 Tạo builder và thêm endpoint thủ công
    let config = Builder::new()
        .region(region)
        .credentials_provider(creds)
        .endpoint_url(endpoint_url) // 👈 dùng endpoint_url thay vì Endpoint
        .force_path_style(true)
        .behavior_version(BehaviorVersion::latest())  // cần cho MinIO
        .build();

    // 🪣 Tạo client
    let client = Client::from_conf(config);
    
    println!("✅ Đã kết nối MinIO");

    Ok(client)
}

/// API test MinIO
#[get("/api/test_minio")]
pub async fn test_minio_connection() -> impl Responder {
    match create_minio_client().await {
        Ok(client) => {
            // 🪣 Lấy danh sách bucket trong MinIO
            match client.list_buckets().send().await {
                Ok(resp) => {
                    let buckets: Vec<_> = resp
                        .buckets
                        .unwrap_or_default()
                        .into_iter()
                        .filter_map(|b| b.name)
                        .collect();

                    HttpResponse::Ok().json(json!({
                        "status": "success",
                        "message": "Kết nối MinIO thành công!",
                        "buckets": buckets
                    }))
                }
                Err(e) => HttpResponse::InternalServerError().json(json!({
                    "status": "error",
                    "message": format!("Không thể lấy danh sách bucket: {}", e)
                })),
            }
        }
        Err(e) => HttpResponse::InternalServerError().json(json!({
            "status": "error",
            "message": format!("Không thể kết nối MinIO: {}", e)
        })),
    }
}
