from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import JSONResponse
import os

# OCR 관련 추가 import
from PIL import Image
import pytesseract
import io

# OpenAI API import
import openai

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

@app.post("/ai_feedback")
async def ai_feedback(text: str = Body(..., embed=True)):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenAI API 키가 환경 변수에 없습니다.")
    openai.api_key = api_key
    prompt = f"""
    아래는 학생이 쓴 글입니다. 이 글을 읽고 학생의 생각을 확장시켜줄 수 있는 질문 또는 코칭을 2개 생성해 주세요. 각 항목은 번호로 구분해 주세요.
    ---
    {text}
    ---
    질문/코칭:
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7
        )
        feedback = response.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 피드백 생성 오류: {str(e)}")
    return {"feedback": feedback}

@app.post("/ai_evaluate")
async def ai_evaluate(text: str = Body(..., embed=True)):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenAI API 키가 환경 변수에 없습니다.")
    openai.api_key = api_key
    prompt = f"""
    아래는 학생이 쓴 글입니다. 이 글을 루브릭 기준에 따라 아래 단계 중 하나로 분류하고, 그 이유와 개선 코멘트를 작성해 주세요.
    [단계]
    1단계: 주제와 관련 없는 글
    2단계: 주제와 관련 있으나 내용이 부족함
    3단계: 주제에 맞는 내용과 근거가 충분함
    ---
    {text}
    ---
    [출력 예시]
    단계: (1/2/3 중 하나)
    코멘트: (간단한 평가 및 개선점)
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7
        )
        result = response.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 평가 생성 오류: {str(e)}")
    return {"evaluation": result}

@app.get("/")
def read_root():
    return {"message": "Hello, AI 학생 글 평가 시스템!"} 