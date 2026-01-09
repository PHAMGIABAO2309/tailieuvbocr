from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict
import uvicorn 

from trichyeujson import extract_document_info

app = FastAPI()

# 🔥 THÊM CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React
    allow_credentials=True,
    allow_methods=["*"],  # POST, OPTIONS
    allow_headers=["*"],
)

class OCRRequest(BaseModel):
    raw_text: str

@app.post("/extract")
def extract_from_ocr(req: OCRRequest) -> Dict:
    result = extract_document_info(req.raw_text)
    return {
        "status": "success",
        "data": result
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
