from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os

# OCR 관련 추가 import
from PIL import Image
import pytesseract
import io

app = FastAPI()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # 파일 확장자 및 크기 체크
    ext = file.filename.split('.')[-1].lower()
    if ext not in ["jpg", "jpeg", "png"]:
        raise HTTPException(status_code=400, detail="jpg, jpeg, png 파일만 업로드 가능합니다.")
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="10MB 이하 파일만 업로드 가능합니다.")
    # 파일 저장 (중복 방지)
    save_name = file.filename
    save_path = os.path.join(UPLOAD_DIR, save_name)
    count = 1
    while os.path.exists(save_path):
        name, ext2 = os.path.splitext(file.filename)
        save_name = f"{name}_{count}{ext2}"
        save_path = os.path.join(UPLOAD_DIR, save_name)
        count += 1
    with open(save_path, "wb") as f:
        f.write(contents)
    return JSONResponse(content={"filename": save_name, "message": "업로드 성공"})

@app.post("/ocr_upload")
async def ocr_upload(file: UploadFile = File(...)):
    ext = file.filename.split('.')[-1].lower()
    if ext not in ["jpg", "jpeg", "png"]:
        raise HTTPException(status_code=400, detail="jpg, jpeg, png 파일만 업로드 가능합니다.")
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="10MB 이하 파일만 업로드 가능합니다.")
    try:
        image = Image.open(io.BytesIO(contents))
        text = pytesseract.image_to_string(image, lang='kor+eng')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR 처리 중 오류 발생: {str(e)}")
    return {"ocr_text": text.strip()}

@app.get("/")
def read_root():
    return {"message": "Hello, AI 학생 글 평가 시스템!"} 