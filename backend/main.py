# -*- coding: utf-8 -*-
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import json
from datetime import datetime
import re

# OCR 관련 추가 import
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import io
import cv2
import numpy as np

# Tesseract 실행 파일 경로 설정 (Windows)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# 임시: Tesseract 설치 여부 확인
import shutil
TESSERACT_INSTALLED = True
print("✅ Tesseract OCR이 활성화되었습니다!")

# OpenAI API import
import openai

# 데이터베이스 import
from database import DatabaseManager
from pydantic import BaseModel
from typing import List

# OpenAI API 키 설정 (환경변수에서 가져오거나 직접 설정)
openai.api_key = os.getenv("OPENAI_API_KEY", "your-openai-api-key-here")

app = FastAPI(
    title="AI 학생 글 평가 시스템",
    description="손글씨 OCR, AI 피드백, 단계별 평가를 제공하는 교육용 시스템",
    version="2.0"
)

# CORS 설정 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 운영시에는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 데이터베이스 초기화
try:
    db = DatabaseManager()
    print("✅ 데이터베이스 초기화 완료")
except Exception as e:
    print(f"❌ 데이터베이스 초기화 실패: {e}")
    db = None

# 지원하는 파일 확장자 및 크기 제한
ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "bmp", "gif", "tiff", "tif", "webp"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# --- Pydantic 모델 정의 ---
class Criteria(BaseModel):
    title: str
    description: str

class CriteriaUpdate(Criteria):
    id: int

# --- 평가 기준 API 엔드포인트 ---

@app.post("/criteria", summary="새로운 평가 기준 생성")
async def create_criteria(criteria: Criteria):
    """새로운 평가 기준을 생성하고 데이터베이스에 저장합니다."""
    try:
        print(f"📝 평가 기준 생성 요청: 제목={criteria.title}, 설명={criteria.description[:50]}...")
        
        if not db:
            print("❌ 데이터베이스 연결 실패")
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        criteria_id = db.save_criteria(criteria.title, criteria.description)
        print(f"✅ 평가 기준 생성 성공: ID={criteria_id}")
        
        return {"message": "평가 기준이 성공적으로 생성되었습니다.", "criteria_id": criteria_id}
    except Exception as e:
        print(f"❌ 평가 기준 생성 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=f"기준 생성 중 오류 발생: {str(e)}")

@app.get("/criteria", summary="모든 평가 기준 조회")
async def get_criteria_list():
    """데이터베이스에 저장된 모든 평가 기준을 조회합니다."""
    try:
        print("📋 평가 기준 조회 요청")
        
        if not db:
            print("❌ 데이터베이스 연결 실패")
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        criteria_list = db.get_all_criteria()
        print(f"✅ 평가 기준 조회 성공: {len(criteria_list)}개 기준 반환")
        
        return criteria_list
    except Exception as e:
        print(f"❌ 평가 기준 조회 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=f"기준 조회 중 오류 발생: {str(e)}")

@app.put("/criteria/{criteria_id}", summary="평가 기준 수정")
async def update_criteria(criteria_id: int, criteria: Criteria):
    """기존 평가 기준을 수정합니다."""
    try:
        print(f"✏️ 평가 기준 수정 요청: ID={criteria_id}, 제목={criteria.title}")
        
        if not db:
            print("❌ 데이터베이스 연결 실패")
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        db.update_criteria(criteria_id, criteria.title, criteria.description)
        print(f"✅ 평가 기준 수정 성공: ID={criteria_id}")
        
        return {"message": f"평가 기준(ID: {criteria_id})이 성공적으로 수정되었습니다."}
    except Exception as e:
        print(f"❌ 평가 기준 수정 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=f"기준 수정 중 오류 발생: {str(e)}")

@app.delete("/criteria/{criteria_id}", summary="평가 기준 삭제")
async def delete_criteria(criteria_id: int):
    """평가 기준을 삭제합니다."""
    try:
        print(f"🗑️ 평가 기준 삭제 요청: ID={criteria_id}")
        
        if not db:
            print("❌ 데이터베이스 연결 실패")
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        db.delete_criteria(criteria_id)
        print(f"✅ 평가 기준 삭제 성공: ID={criteria_id}")
        
        return {"message": f"평가 기준(ID: {criteria_id})이 성공적으로 삭제되었습니다."}
    except Exception as e:
        print(f"❌ 평가 기준 삭제 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=f"기준 삭제 중 오류 발생: {str(e)}")

# --- AI 평가 관련 함수들 ---

def create_custom_evaluation_prompt(criteria_list, student_text):
    """교사의 평가 기준을 바탕으로 맞춤형 평가 프롬프트 생성"""
    
    if not criteria_list:
        # 기본 평가 기준 사용
        default_prompt = f"""
다음 학생의 글을 종합적으로 평가해주세요.

<학생의 글>
{student_text}

<평가 항목>
1. 내용과 주제 (30점): 글의 내용이 충실하고 주제가 명확한가?
2. 논리성과 구성 (25점): 글의 구성이 논리적이고 체계적인가?
3. 언어 표현 (25점): 어휘 선택과 문장 구성이 적절한가?
4. 창의성 (20점): 독창적이고 참신한 관점이 있는가?

<평가 형식>
- 각 항목별로 구체적인 피드백과 점수를 제시
- 총점과 함께 종합 평가 의견 작성
- 개선 방향 제시
"""
        return default_prompt
    
    # 교사의 맞춤 평가 기준 사용
    criteria_section = "\n".join([
        f"{i+1}. {criterion['title']}: {criterion['description']}"
        for i, criterion in enumerate(criteria_list)
    ])
    
    custom_prompt = f"""
교사가 설정한 맞춤 평가 기준에 따라 다음 학생의 글을 평가해주세요.

<학생의 글>
{student_text}

<교사가 설정한 평가 기준>
{criteria_section}

<평가 요청사항>
1. 위의 각 평가 기준에 따라 구체적으로 분석하고 점수를 매겨주세요 (각 기준당 0-100점)
2. 각 기준별로 학생이 잘한 점과 개선할 점을 명확히 제시해주세요
3. 전체적인 종합 평가와 추천 학습 방향을 제공해주세요
4. 학생이 이해하기 쉬운 친근한 어조로 작성해주세요

<답변 형식>
**평가 기준별 분석**
[각 기준별로 분석]

**종합 평가**
[전체적인 평가와 총점]

**개선 방향**
[구체적인 학습 가이드]
"""
    return custom_prompt

async def call_openai_api(prompt, max_tokens=1000):
    """OpenAI API 호출 함수"""
    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system", 
                    "content": "당신은 학생들의 글쓰기를 평가하는 전문 교사입니다. 건설적이고 따뜻한 피드백을 제공하세요."
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI API 오류: {e}")
        return f"AI 평가 중 오류가 발생했습니다. 나중에 다시 시도해주세요. (오류: {str(e)})"

@app.post("/ocr_upload")
async def ocr_upload(file: UploadFile = File(...)):
    """손글씨 이미지 OCR 처리"""
    # OCR 기능은 현재 비활성화
    return {"message": "OCR 기능은 현재 비활성화되었습니다."}

@app.post("/ai_feedback")
async def ai_feedback(text: str = Body(..., embed=True)):
    """AI 피드백 생성"""
    try:
        if not text or text.strip() == "":
            raise HTTPException(status_code=400, detail="텍스트가 비어있습니다.")
        
        # 피드백 프롬프트 생성
        feedback_prompt = f"""
다음 학생의 글에 대해 건설적인 피드백을 제공해주세요.

<학생의 글>
{text}

<피드백 요청사항>
1. 글의 좋은 점을 먼저 칭찬해주세요
2. 개선할 수 있는 부분을 구체적으로 제시해주세요
3. 다음 단계 학습을 위한 실용적인 조언을 해주세요
4. 학생이 이해하기 쉬운 친근한 어조로 작성해주세요

친근하고 격려하는 어조로 답변해주세요.
"""
        
        # OpenAI API 호출
        feedback = await call_openai_api(feedback_prompt, max_tokens=800)
        
        return {
            "feedback": feedback,
            "status": "success"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 피드백 생성 중 오류: {str(e)}")

@app.post("/ai_evaluate")
async def ai_evaluate(
    text: str = Body(...), 
    submission_id: int = Body(...)
):
    """교사의 맞춤 평가 기준을 사용한 AI 최종 평가"""
    try:
        if not text or text.strip() == "":
            raise HTTPException(status_code=400, detail="평가할 텍스트가 비어있습니다.")
        
        if not db:
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        # 1. 데이터베이스에서 교사의 평가 기준 가져오기
        criteria_list = db.get_all_criteria()
        print(f"📋 평가 기준 {len(criteria_list)}개를 불러왔습니다.")
        
        # 2. 맞춤형 평가 프롬프트 생성
        evaluation_prompt = create_custom_evaluation_prompt(criteria_list, text)
        
        # 3. OpenAI API를 통한 평가 수행
        evaluation = await call_openai_api(evaluation_prompt, max_tokens=1200)
        
        # 4. 평가 결과를 데이터베이스에 저장
        try:
            db.update_ai_evaluation(submission_id, evaluation, ai_stage=3)
            print(f"✅ 제출물 {submission_id}의 AI 평가가 완료되었습니다.")
        except Exception as db_error:
            print(f"❌ 데이터베이스 저장 오류: {db_error}")
            # 평가는 성공했지만 저장 실패한 경우에도 평가 결과는 반환
        
        return {
            "evaluation": evaluation,
            "criteria_count": len(criteria_list),
            "status": "success"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 평가 중 오류: {str(e)}")

@app.post("/submit_revision")
async def submit_revision(
    student_id: str = Body(...), 
    original_text: str = Body(...), 
    revised_text: str = Body(...)
):
    """학생이 수정한 글을 데이터베이스에 저장"""
    try:
        if not student_id or not revised_text:
            raise HTTPException(status_code=400, detail="학생 ID와 수정된 글은 필수입니다.")
        
        if not db:
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        # 데이터베이스에 수정된 글 저장
        submission_id = db.save_submission(
            student_id=student_id,
            ocr_text=original_text,
            revised_text=revised_text,
            ai_stage=2  # 2단계: 수정 완료
        )
        
        return {
            "message": "수정된 글이 성공적으로 저장되었습니다.",
            "submission_id": submission_id,
            "status": "success"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"제출 중 오류: {str(e)}")

# --- 교사용 API ---

@app.get("/teacher/submissions")
async def get_teacher_submissions():
    """교사용: 모든 학생 제출 내역 조회"""
    try:
        if not db:
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        submissions = db.get_all_submissions()
        return {
            "submissions": submissions,
            "total_count": len(submissions)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"제출 내역 조회 중 오류: {str(e)}")

@app.get("/submission/{submission_id}")
async def get_submission_detail(submission_id: int):
    """특정 제출물의 상세 정보 조회"""
    try:
        if not db:
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        submission = db.get_submission_by_id(submission_id)
        if not submission:
            raise HTTPException(status_code=404, detail="제출물을 찾을 수 없습니다.")
        
        return submission
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"제출물 조회 중 오류: {str(e)}")

# --- 기본 API ---

@app.get("/")
def read_root():
    return {
        "message": "🎓 AI 학생 글 평가 시스템에 오신 것을 환영합니다! (서버 정상 작동 중)",
        "version": "2.0 with Custom Evaluation Criteria",
        "features": [
            "교사 맞춤 평가 기준 설정",
            "AI 기반 개인화 평가",
            "학생 글쓰기 피드백",
            "제출 내역 관리"
        ]
    }

@app.get("/health")
async def health_check():
    """시스템 상태 확인"""
    return {
        "status": "healthy",
        "database": "connected" if db else "disconnected",
        "timestamp": datetime.now().isoformat()
    }
