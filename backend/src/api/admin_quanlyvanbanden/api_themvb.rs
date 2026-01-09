use actix_web::{post, web, HttpResponse, Responder};
use sqlx::MySqlPool;
use serde::Deserialize;
use serde_json::json;

#[derive(Deserialize)]
pub struct AddDocument {
    pub title: String,
    pub path: String,
}

// SQL insert
pub const INSERT_FILES_SQL: &str = "INSERT INTO files (FileCode, Title, path) VALUES (?, ?, ?)";
pub const INSERT_IDO_SQL: &str = "INSERT INTO infomation_documents_out (InfoId, FileCode) VALUES (?, ?)";
pub const INSERT_DOCUMENTS_EN_SQL: &str = "INSERT INTO documents_eng (LanId, InfoId) VALUES ('EN', ?)";

// Endpoint thêm văn bản
#[post("/api/admin/add_documents")]
pub async fn post_admin_add_documents(
    db_pool: web::Data<MySqlPool>,
    form: web::Json<AddDocument>,
) -> impl Responder {
    match handle_insert_document(db_pool, form).await {
        Ok(_) => HttpResponse::Ok().json(json!({
            "success": true,
            "message": "Thêm văn bản thành công"
        })),
        Err(e) => HttpResponse::InternalServerError().json(json!({
            "success": false,
            "message": format!("Lỗi: {}", e)
        })),
    }
}

async fn handle_insert_document(
    db_pool: web::Data<MySqlPool>,
    form: web::Json<AddDocument>,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut tx = db_pool.begin().await?;

    // 1️⃣ Lấy mã FileCode mới
    let last_filecode: Option<(String,)> = sqlx::query_as("SELECT FileCode FROM files ORDER BY CAST(SUBSTRING(FileCode, 3) AS UNSIGNED) DESC LIMIT 1")
        .fetch_optional(&mut *tx)
        .await?;
    
    let next_filecode = if let Some((last,)) = last_filecode {
        let num = last[2..].parse::<u32>()? + 1;
        format!("HS{:03}", num)
    } else {
        "HS001".to_string()
    };

    // 2️⃣ Thêm vào bảng files
    sqlx::query(INSERT_FILES_SQL)
        .bind(&next_filecode)
        .bind(&form.title)
        .bind(&form.path)
        .execute(&mut *tx)
        .await?;

    // 3️⃣ Lấy InfoId mới
    let last_infoid: Option<(String,)> = sqlx::query_as("SELECT InfoId FROM infomation_documents_out ORDER BY CAST(SUBSTRING(InfoId, 3) AS UNSIGNED) DESC LIMIT 1")
        .fetch_optional(&mut *tx)
        .await?;

    let next_infoid = if let Some((last,)) = last_infoid {
        let num = last[2..].parse::<u32>()? + 1;
        format!("TT{:03}", num)
    } else {
        "TT001".to_string()
    };

    // 4️⃣ Thêm vào bảng infomation_documents_out
    sqlx::query(INSERT_IDO_SQL)
        .bind(&next_infoid)
        .bind(&next_filecode)
        .execute(&mut *tx)
        .await?;

    // 5️⃣ Thêm vào documents_eng
    sqlx::query(INSERT_DOCUMENTS_EN_SQL)
        .bind(&next_infoid)
        .execute(&mut *tx)
        .await?;

    tx.commit().await?;
    Ok(())
}
