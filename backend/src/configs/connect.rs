use dotenvy::dotenv;
use sqlx::{MySql, Pool, Row};
use sqlx::Column;
use serde_json::Value;
use std::env;

pub async fn ketnoi_cosodulieu() -> (Pool<MySql>,  String) {
    dotenv().ok();

    let db_url = env::var("DATABASE_URL").expect("Thiếu DATABASE_URL");
    let host = env::var("HOST").unwrap_or("127.0.0.1".into());
    let port = env::var("PORT").unwrap_or("3000".into());
    let address = format!("{host}:{port}");
    let gemini_api_key = env::var("REACT_APP_GEMINI_API_KEY").expect("GEMINI_API_KEY không tồn tại");

    let pool = Pool::connect(&db_url).await.expect("Kết nối MySQL thất bại");
     println!("🔐 Gemini API Key: {}...", &gemini_api_key[..10]);

    println!("✅ Đã kết nối MySQL");

    (pool,  address)
}


pub async fn thucthi_truyvan(pool: &Pool<MySql>, query: &str) -> Result<Vec<Value>, sqlx::Error> {
    let rows = sqlx::query(query).fetch_all(pool).await?;
    let mut results = Vec::new();

    for row in rows {
        let mut json_row = serde_json::Map::new();
        for (i, column) in row.columns().iter().enumerate() {
            let col_name = column.name();
            let value: Option<String> = row.try_get(i).unwrap_or(None);
            json_row.insert(col_name.to_string(), serde_json::json!(value));
        }
        results.push(serde_json::Value::Object(json_row));
    }

    Ok(results)
}