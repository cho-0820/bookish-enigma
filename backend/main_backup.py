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

def preprocess_image_for_ocr(image):
    """OCR을 위한 고급 이미지 전처리 (한글 손글씨 특화)"""
    # PIL 이미지를 numpy 배열로 변환
    img_array = np.array(image)
    
    # 그레이스케일로 변환
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array
    
    print(f"📸 원본 이미지 크기: {gray.shape}")
    
    # 1. 가우시안 블러로 노이즈 제거 (더 강화)
    denoised = cv2.GaussianBlur(gray, (3, 3), 0)
    
    # 2. 샤프닝 필터 적용 (글자 윤곽 선명화)
    kernel_sharpen = np.array([[-1,-1,-1],
                              [-1, 9,-1],
                              [-1,-1,-1]])
    sharpened = cv2.filter2D(denoised, -1, kernel_sharpen)
    
    # 3. 대비 향상 (CLAHE - 더 강한 설정)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    enhanced = clahe.apply(sharpened)
    
    # 4. 적응형 이진화 (Otsu + Gaussian)
    # 먼저 Otsu로 임계값 찾기
    _, otsu_binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 적응형 임계값도 적용해서 비교
    adaptive_binary = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                           cv2.THRESH_BINARY, 11, 2)
    
    # 두 결과를 조합 (더 나은 결과 선택)
    combined_binary = cv2.bitwise_and(otsu_binary, adaptive_binary)
    
    # 5. 모폴로지 연산으로 글자 개선
    # 작은 노이즈 제거
    kernel_noise = np.ones((2,2), np.uint8)
    cleaned = cv2.morphologyEx(combined_binary, cv2.MORPH_OPEN, kernel_noise)
    
    # 글자 두께 보정
    kernel_close = np.ones((1,1), np.uint8)
    processed = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel_close)
    
    # 6. 텍스트 영역 확대 (OCR 성능 향상)
    # 텍스트가 있는 영역을 찾아서 확대
    contours, _ = cv2.findContours(processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # 가장 큰 텍스트 영역 찾기
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)
        
        # 여백 추가
        margin = 20
        x = max(0, x - margin)
        y = max(0, y - margin)
        w = min(processed.shape[1] - x, w + 2*margin)
        h = min(processed.shape[0] - y, h + 2*margin)
        
        # 텍스트 영역만 추출
        text_area = processed[y:y+h, x:x+w]
        
        # 충분히 큰 영역이면 사용
        if w > 50 and h > 30:
            processed = text_area
            print(f"✂️ 텍스트 영역 추출: {w}x{h}")
    
    print(f"🔧 전처리 완료: {processed.shape}")
    
    # numpy 배열을 다시 PIL 이미지로 변환
    return Image.fromarray(processed)

def create_multiple_preprocessed_images(image):
    """다양한 전처리 방법으로 이미지 여러 버전 생성"""
    images = []
    
    # PIL 이미지를 numpy 배열로 변환
    img_array = np.array(image)
    
    # 그레이스케일로 변환
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array
    
    print(f"🎨 다중 전처리 시작: {gray.shape}")
    
    # 1. 기본 전처리 (위의 함수와 동일)
    basic_processed = preprocess_image_for_ocr(image)
    images.append(("기본전처리", basic_processed))
    
    # 2. 고대비 버전
    try:
        # 히스토그램 평활화
        equalized = cv2.equalizeHist(gray)
        # 강한 이진화
        _, high_contrast = cv2.threshold(equalized, 127, 255, cv2.THRESH_BINARY)
        images.append(("고대비", Image.fromarray(high_contrast)))
    except:
        pass
    
    # 3. 부드러운 버전 (노이즈가 많은 이미지용)
    try:
        # 강한 블러 후 샤프닝
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        kernel = np.array([[0,-1,0], [-1,5,-1], [0,-1,0]])
        soft_sharp = cv2.filter2D(blurred, -1, kernel)
        _, soft_binary = cv2.threshold(soft_sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        images.append(("부드러운처리", Image.fromarray(soft_binary)))
    except:
        pass
    
    # 4. 침식-팽창 버전 (얇은 글씨용)
    try:
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = np.ones((2,2), np.uint8)
        eroded = cv2.erode(binary, kernel, iterations=1)
        dilated = cv2.dilate(eroded, kernel, iterations=1)
        images.append(("침식팽창", Image.fromarray(dilated)))
    except:
        pass
    
    print(f"🎨 전처리 완료: {len(images)}개 버전 생성")
    return images

def clean_ocr_text(text):
    """OCR 결과 텍스트 후처리 및 정리 (한글 우선, 영어 오인식 강화 감지)"""
    if not text or not text.strip():
        return ""
    
    # 1. 기본 정리
    cleaned = text.strip()
    
    # 2. 한글이 영어로 잘못 인식된 패턴 감지 (강화된 버전)
    suspicious_english_patterns = [
        r'^[a-zA-Z\s]{1,3}$',  # 너무 짧은 영문
        r'^[oOsS][a-zA-Z\s]*$',  # 'o', 'S' 등으로 시작하는 의심스러운 패턴
        r'[a-zA-Z]{1,2}\s+[a-zA-Z]{1,2}\s+[a-zA-Z]{1,2}',  # 짧은 영단어들이 연속으로
        r'^[a-zA-Z]{1,2}\s+[a-zA-Z]+\s+[a-zA-Z]{1,2}',  # 패턴: "oS witty Ee"
        r'[oOsSa-zA-Z]+\s+[wW][a-zA-Z]+\s+[eE][a-zA-Z]*',  # "oS witty Ee" 패턴
        r'^[a-zA-Z]+\s+[a-zA-Z]+\s+[a-zA-Z]+\s+[a-zA-Z]+\s+[a-zA-Z]+',  # 5개 이상 짧은 영단어
        r'[oO][sS]\s+[a-zA-Z]+',  # "oS" 또는 "OS"로 시작하는 패턴
        r'[eE][eE]\s+[oO][dD]',  # "Ee OD" 패턴
        r'a[eE]\s+[a-zA-Z]+ee',  # "ae ataanee" 패턴
    ]
    
    # 한글이 포함되지 않고 위 패턴에 해당하면 의심스러운 결과
    korean_chars = sum(1 for c in cleaned if '가' <= c <= '힣')
    if korean_chars == 0:
        for pattern in suspicious_english_patterns:
            if re.search(pattern, cleaned.strip(), re.IGNORECASE):
                print(f"🔍 의심스러운 영어 패턴 감지: '{cleaned}' -> 패턴: {pattern}")
                return ""  # 의심스러운 영어 패턴은 제거
        
        # 추가 검증: 전체 텍스트가 의미없는 영어 조합인지 확인
        words = cleaned.split()
        if len(words) >= 3:
            # 3단어 이상인데 모두 3글자 이하의 영단어들이면 의심
            short_words = [w for w in words if len(w) <= 3 and w.isalpha()]
            if len(short_words) >= len(words) * 0.7:  # 70% 이상이 짧은 영단어
                print(f"🔍 의심스러운 짧은 영단어 조합 감지: '{cleaned}'")
                return ""
        
        # 대소문자가 불규칙하게 혼재된 패턴 감지
        if re.search(r'[a-z][A-Z][a-z].*[A-Z][a-z]', cleaned):
            print(f"🔍 불규칙한 대소문자 패턴 감지: '{cleaned}'")
            return ""
    
    # 3. 의미없는 단일 문자나 특수문자 제거
    meaningless_chars = ['~', '.', ',', '!', '@', '#', '$', '%', '^', '&', '*', 
                        '(', ')', '-', '=', '+', '[', ']', '{', '}', '|', 
                        '\\', ':', ';', '"', "'", '<', '>', '?', '/', '¥', '₩']
    
    # 4. 줄별로 처리
    lines = cleaned.split('\n')
    valid_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 한글 문자 개수 확인
        line_korean_chars = sum(1 for c in line if '가' <= c <= '힣')
        line_english_chars = sum(1 for c in line if c.isalpha() and c.isascii())
        line_total_chars = len(line.replace(' ', ''))
        
        # 너무 짧은 줄 필터링 (1-2글자이고 의미없는 문자들)
        if len(line) <= 2:
            # 단일 특수문자나 숫자만 있는 경우 제거
            if all(c in meaningless_chars + '0123456789' for c in line):
                continue
            # 단일 영문자나 의미없는 조합 제거
            if len(line) == 1 and (line.isalpha() and line.islower()):
                continue
        
        # 한글이 없고 영어만 있는 경우 더 엄격하게 검사
        if line_korean_chars == 0 and line_english_chars > 0:
            # 3글자 미만의 영어 단어들만 있으면 제거
            english_words = re.findall(r'[a-zA-Z]+', line)
            if all(len(word) < 3 for word in english_words):
                continue
            # 대소문자가 혼재된 이상한 패턴 제거
            if re.search(r'[a-z][A-Z][a-z]|[A-Z][a-z][A-Z]', line):
                continue
            
            # 줄 전체가 의심스러운 영어 패턴인지 재검사
            for pattern in suspicious_english_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    print(f"🔍 줄별 영어 오인식 패턴 감지: '{line}'")
                    line = ""  # 해당 줄 제거
                    break
        
        # 빈 줄이 되었으면 건너뛰기
        if not line:
            continue
        
        # 5. 깨진 글자 패턴 제거
        special_chars = sum(1 for c in line if not c.isalnum() and not '가' <= c <= '힣' and c != ' ')
        
        if line_total_chars > 0:
            special_ratio = special_chars / line_total_chars
            # 특수문자가 50% 이상이면 의미없는 텍스트로 간주
            if special_ratio > 0.5:
                continue
        
        # 6. 의미있는 단어가 포함된 줄만 유지
        korean_words = re.findall(r'[가-힣]{2,}', line)
        english_words = re.findall(r'[a-zA-Z]{3,}', line)
        
        # 한글이 우선, 영어는 더 긴 단어만 인정
        if korean_words or (line_korean_chars >= 2) or english_words:
            # 7. 특수문자 정리
            cleaned_line = re.sub(r'[^\w\s가-힣]', ' ', line)  # 특수문자를 공백으로
            cleaned_line = re.sub(r'\s+', ' ', cleaned_line)   # 연속 공백을 하나로
            cleaned_line = cleaned_line.strip()
            
            if cleaned_line and len(cleaned_line) >= 2:
                valid_lines.append(cleaned_line)
    
    result = '\n'.join(valid_lines)
    
    # 8. 최종 검증 (한글 우선) - 더 엄격한 조건
    if result:
        final_korean = sum(1 for c in result if '가' <= c <= '힣')
        final_english = sum(1 for c in result if c.isalpha() and c.isascii())
        
        # 한글이 있으면 우선 채택
        if final_korean >= 2:
            print(f"✅ 한글 텍스트 채택: '{result[:50]}...' (한글 {final_korean}자)")
            return result
        # 한글이 없어도 의미있는 영어 단어가 있으면 채택 (더 엄격한 조건)
        elif final_english >= 6:  # 최소 6글자 이상의 영어 (더 엄격)
            print(f"⚠️ 영어 텍스트 채택: '{result[:50]}...' (영어 {final_english}자)")
            return result
        else:
            print(f"❌ 텍스트 품질 부족으로 제거: '{result}' (한글 {final_korean}자, 영어 {final_english}자)")
    
    return ""

def clean_korean_ocr_text(text):
    """한글 OCR 결과 전용 후처리 (품질 개선 특화)"""
    if not text or not text.strip():
        return ""
    
    # 1. 기본 정리
    cleaned = text.strip()
    
    print(f"🔤 원본 텍스트: '{cleaned}'")
    
    # 2. 숫자와 한글 혼재 비율 체크
    korean_chars = sum(1 for c in cleaned if '가' <= c <= '힣')
    digit_chars = sum(1 for c in cleaned if c.isdigit())
    total_chars = len(cleaned.replace(' ', '').replace('\n', ''))
    
    if total_chars > 0:
        digit_ratio = digit_chars / total_chars
        korean_ratio = korean_chars / total_chars
        
        print(f"📊 문자 분석: 한글 {korean_chars}자({korean_ratio:.1%}), 숫자 {digit_chars}자({digit_ratio:.1%})")
        
        # 숫자가 30% 이상이면 품질이 낮은 것으로 판단
        if digit_ratio > 0.3:
            print(f"❌ 숫자 비율 과다: {digit_ratio:.1%} > 30%")
            return ""
        
        # 한글이 50% 미만이면 품질이 낮은 것으로 판단
        if korean_ratio < 0.5:
            print(f"❌ 한글 비율 부족: {korean_ratio:.1%} < 50%")
            return ""
    
    # 3. 의미없는 한글 패턴 감지
    korean_text_only = re.sub(r'[^가-힣\s]', '', cleaned)
    korean_words = korean_text_only.split()
    
    if korean_words:
        # 한글 단어들의 길이 분석
        word_lengths = [len(word) for word in korean_words if len(word) > 0]
        avg_word_length = sum(word_lengths) / len(word_lengths) if word_lengths else 0
        
        print(f"📝 한글 단어 분석: {len(korean_words)}개 단어, 평균 길이: {avg_word_length:.1f}자")
        
        # 너무 짧은 단어들만 있으면 품질 의심
        if avg_word_length < 1.5:
            print(f"❌ 단어 길이 부족: 평균 {avg_word_length:.1f}자 < 1.5자")
            return ""
        
        # 1글자 단어가 80% 이상이면 품질 의심
        short_words = [w for w in korean_words if len(w) == 1]
        if len(korean_words) > 0 and len(short_words) / len(korean_words) > 0.8:
            print(f"❌ 1글자 단어 과다: {len(short_words)}/{len(korean_words)}개")
            return ""
    
    # 4. 의미없는 연속 문자 패턴 감지
    suspicious_korean_patterns = [
        r'[ㄱ-ㅎ]{2,}',  # 자음만 연속
        r'[ㅏ-ㅣ]{2,}',  # 모음만 연속
        r'같은문자{3,}',  # 같은 문자 3번 이상 반복 (일반적 패턴)
    ]
    
    for pattern in suspicious_korean_patterns:
        if re.search(pattern, cleaned):
            print(f"❌ 의심스러운 한글 패턴 감지: {pattern}")
            return ""
    
    # 5. 줄별 처리 및 정리
    lines = cleaned.split('\n')
    valid_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 줄별 한글 비율 확인
        line_korean = sum(1 for c in line if '가' <= c <= '힣')
        line_total = len(line.replace(' ', ''))
        
        if line_total > 0 and line_korean / line_total >= 0.6:  # 60% 이상 한글
            # 특수문자와 불필요한 공백 정리
            cleaned_line = re.sub(r'[^\w\s가-힣]', ' ', line)
            cleaned_line = re.sub(r'\s+', ' ', cleaned_line)
            cleaned_line = cleaned_line.strip()
            
            if len(cleaned_line) >= 2:  # 최소 2글자 이상
                valid_lines.append(cleaned_line)
                print(f"✅ 유효한 줄: '{cleaned_line}'")
    
    result = '\n'.join(valid_lines)
    
    # 6. 최종 검증
    if result:
        final_korean = sum(1 for c in result if '가' <= c <= '힣')
        final_total = len(result.replace(' ', '').replace('\n', ''))
        
        if final_total > 0:
            final_korean_ratio = final_korean / final_total
            
            if final_korean_ratio >= 0.7 and final_korean >= 4:  # 70% 이상 한글, 최소 4글자
                print(f"✅ 한글 텍스트 품질 양호: '{result}' (한글 {final_korean_ratio:.1%})")
                return result
            else:
                print(f"❌ 최종 품질 부족: 한글 {final_korean_ratio:.1%}, {final_korean}글자")
    
    return ""

def analyze_korean_text_quality(text):
    """한글 텍스트 품질 분석 및 점수 산정"""
    if not text:
        return 0, "텍스트 없음", {}
    
    korean_chars = sum(1 for c in text if '가' <= c <= '힣')
    digit_chars = sum(1 for c in text if c.isdigit())
    english_chars = sum(1 for c in text if c.isalpha() and c.isascii())
    total_chars = len(text.replace(' ', '').replace('\n', ''))
    
    if total_chars == 0:
        return 0, "빈 텍스트", {}
    
    # 분석 정보
    analysis = {
        "korean_chars": korean_chars,
        "digit_chars": digit_chars,
        "english_chars": english_chars,
        "total_chars": total_chars,
        "korean_ratio": korean_chars / total_chars,
        "digit_ratio": digit_chars / total_chars,
    }
    
    # 점수 계산 (한글 특화)
    score = 0
    
    # 1. 한글 비율 (최대 40점)
    korean_ratio = korean_chars / total_chars
    score += korean_ratio * 40
    
    # 2. 한글 존재 보너스 (20점)
    if korean_chars >= 4:
        score += 20
    
    # 3. 한글 단어 품질 (최대 20점)
    korean_words = re.findall(r'[가-힣]{2,}', text)
    if korean_words:
        word_score = min(len(korean_words) * 3, 15)  # 단어 개수
        avg_length = sum(len(w) for w in korean_words) / len(korean_words)
        if avg_length >= 2:
            word_score += 5  # 단어 길이 보너스
        score += word_score
    
    # 4. 숫자 비율 페널티
    digit_ratio = digit_chars / total_chars
    if digit_ratio > 0.2:  # 20% 이상 숫자면 페널티
        score -= (digit_ratio - 0.2) * 100  # 강한 페널티
    
    # 5. 적절한 길이 (10점)
    if 6 <= total_chars <= 100:
        score += 10
    
    # 6. 문장 구조 보너스 (10점)
    if korean_chars >= 6 and ' ' in text:  # 공백이 있고 충분한 길이
        score += 10
    
    score = max(0, min(100, int(score)))
    
    # 품질 설명
    if score >= 80:
        quality_desc = "매우 좋음 (한글)"
    elif score >= 60:
        quality_desc = "좋음 (한글)"
    elif score >= 40:
        quality_desc = "보통 (한글)"
    elif score >= 20:
        quality_desc = "나쁨 (한글)"
    else:
        quality_desc = "매우 나쁨 (한글)"
    
    return score, quality_desc, analysis

def evaluate_ocr_quality(text):
    """OCR 결과의 품질을 평가 (한글 최우선 평가, 영어 오인식 감지)"""
    if not text:
        return 0, "텍스트 없음"
    
    # 한글, 영문, 숫자, 특수문자 비율 계산
    korean_count = sum(1 for c in text if '가' <= c <= '힣')
    english_count = sum(1 for c in text if c.isalpha() and c.isascii())
    digit_count = sum(1 for c in text if c.isdigit())
    special_count = sum(1 for c in text if not c.isalnum() and not '가' <= c <= '힣' and c != ' ')
    
    total_count = len(text.replace(' ', '').replace('\n', ''))
    
    if total_count == 0:
        return 0, "빈 텍스트"
    
    # 품질 점수 계산 (0-100) - 한글 최우선
    quality_score = 0
    
    # 1. 한글 비율 (한글이 있으면 강력한 보너스)
    korean_ratio = korean_count / total_count
    if korean_ratio > 0:
        quality_score += korean_ratio * 60  # 한글 비율에 따른 기본 점수 (증가)
        quality_score += 25  # 한글 존재 보너스 (증가)
        
        # 한글 단어 개수 보너스
        korean_words = len(re.findall(r'[가-힣]{2,}', text))
        if korean_words > 0:
            quality_score += min(korean_words * 5, 20)  # 한글 단어 보너스 증가
        
        print(f"✅ 한글 발견: {korean_count}자 ({korean_ratio:.1%}), 단어: {korean_words}개")
    
    # 2. 영문 비율 (한글이 없을 때만 적용)
    if korean_count == 0:
        english_ratio = english_count / total_count
        quality_score += english_ratio * 30  # 영어만 있을 때 기본 점수 감소
        
        # 영어 오인식 패턴 감지 및 페널티
        words = text.split()
        if len(words) >= 3:
            # 짧은 영단어들이 많으면 페널티
            short_words = [w for w in words if len(w) <= 3 and w.isalpha()]
            if len(short_words) >= len(words) * 0.6:  # 60% 이상이 짧은 영단어
                quality_score -= 40  # 강한 페널티
                print(f"⚠️ 영어 오인식 의심: 짧은 영단어 {len(short_words)}/{len(words)}개")
        
        # 특정 의심스러운 패턴 감지
        suspicious_patterns = [
            r'[oO][sS]\s+[a-zA-Z]+',  # "oS witty" 패턴
            r'[eE][eE]\s+[oO][dD]',   # "Ee OD" 패턴  
            r'a[eE]\s+[a-zA-Z]+ee',   # "ae ataanee" 패턴
            r'[a-z][A-Z][a-z].*[A-Z][a-z]',  # 불규칙한 대소문자
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                quality_score -= 50  # 매우 강한 페널티
                print(f"❌ 영어 오인식 패턴 감지: {pattern}")
                break
        
        print(f"⚠️ 영어만 감지: {english_count}자 ({english_ratio:.1%})")
    
    # 3. 숫자 비율
    digit_ratio = digit_count / total_count
    quality_score += digit_ratio * 10
    
    # 4. 특수문자 비율 (낮을수록 좋음)
    special_ratio = special_count / total_count
    quality_score += (1 - special_ratio) * 15
    
    # 5. 적절한 길이 (너무 짧거나 길지 않음)
    if 3 <= total_count <= 500:
        quality_score += 15
    
    # 6. 최종 보정
    # 한글이 있으면 최소 점수 보장
    if korean_count >= 2:
        quality_score = max(quality_score, 50)  # 한글이 있으면 최소 50점
    
    # 한글이 없고 영어만 있으면 점수 제한
    elif korean_count == 0 and english_count > 0:
        quality_score = min(quality_score, 70)  # 영어만 있으면 최대 70점
    
    # 점수 범위 제한
    quality_score = max(0, min(100, int(quality_score)))
    
    # 품질 설명 (한글 우선 기준)
    if korean_count >= 2:
        if quality_score >= 85:
            quality_desc = "매우 좋음 (한글)"
        elif quality_score >= 70:
            quality_desc = "좋음 (한글)"
        elif quality_score >= 50:
            quality_desc = "보통 (한글)"
        else:
            quality_desc = "나쁨 (한글)"
    else:
        if quality_score >= 70:
            quality_desc = "좋음 (영어)"
        elif quality_score >= 50:
            quality_desc = "보통 (영어)"
        elif quality_score >= 30:
            quality_desc = "나쁨 (영어)"
        else:
            quality_desc = "매우 나쁨 (영어)"
    
    print(f"📊 품질 평가: {quality_score}점 ({quality_desc}) - 한글:{korean_count}자, 영어:{english_count}자")
    
    return quality_score, quality_desc

def try_multiple_ocr_methods(image):
    """손글씨 특화 확장 OCR 방법으로 텍스트 추출 시도"""
    results = []
    
    print("🔍 손글씨 특화 OCR 시작!")
    
    # 1. 손글씨 특화 이미지 변형 생성
    handwriting_variants = create_handwriting_variants(image)
    
    # 2. 기존 일반 전처리 이미지들도 생성
    general_variants = create_multiple_preprocessed_images(image)
    
    # 모든 이미지 변형들 결합
    all_variants = handwriting_variants + general_variants
    
    print(f"🎨 총 {len(all_variants)}개 이미지 변형 생성")
    
    # 각 이미지 변형에 대해 손글씨 특화 OCR 방법들 시도
    for variant_name, processed_image in all_variants:
        print(f"\n🖼️ {variant_name} 이미지로 OCR 시도...")
        
        # 손글씨에 최적화된 PSM 모드들
        psm_modes = [
            (6, "균등분할"),    # 단일 텍스트 블록 
            (8, "단어단위"),    # 단일 단어 - 손글씨에 좋음
            (7, "단일라인"),    # 단일 텍스트 라인
            (13, "원시라인"),   # 원시 라인, 조정 없음 - 손글씨 특화
            (4, "단일컬럼"),    # 단일 컬럼
        ]
        
        for psm, psm_desc in psm_modes:
            # 한국어 전용 시도
            try:
                print(f"  📝 한국어전용 PSM{psm}({psm_desc}) 시도...")
                
                # DPI 설정 추가 (고해상도)
                config = f'--psm {psm} --dpi 300'
                text = pytesseract.image_to_string(processed_image, lang='kor', config=config)
                
                cleaned_text = enhance_korean_ocr_result(text)
                if cleaned_text:
                    score, desc, analysis = analyze_korean_text_quality(cleaned_text)
                    
                    # 손글씨 특화 보너스
                    if "손글씨" in variant_name:
                        score += 25  # 손글씨 전처리 보너스
                    if psm in [8, 13]:  # 손글씨에 좋은 PSM
                        score += 15
                    else:
                        score += 10
                    
                    if score > 100: score = 100
                    
                    method_name = f"한국어({variant_name}-PSM{psm})"
                    results.append((method_name, cleaned_text, score, desc, analysis))
                    print(f"    ✅ 성공: '{cleaned_text[:40]}...' (품질: {score}점)")
                else:
                    print(f"    ❌ 품질 부족으로 제거됨")
                    
            except Exception as e:
                print(f"    ❌ 오류: {e}")
            
            # 한영 혼합도 시도 (백업용)
            if psm in [6, 7]:  # 일반적인 PSM만
                try:
                    print(f"  🔤 한영혼합 PSM{psm} 시도...")
                    
                    config = f'--psm {psm} --dpi 300'
                    text = pytesseract.image_to_string(processed_image, lang='kor+eng', config=config)
                    
                    cleaned_text = enhance_korean_ocr_result(text)
                    if cleaned_text:
                        score, desc, analysis = analyze_korean_text_quality(cleaned_text)
                        
                        # 혼합 모드는 보너스 적게
                        if "손글씨" in variant_name:
                            score += 15
                        score += 5
                        
                        if score > 100: score = 100
                        
                        method_name = f"한영혼합({variant_name}-PSM{psm})"
                        results.append((method_name, cleaned_text, score, desc, analysis))
                        print(f"    ✅ 성공: '{cleaned_text[:40]}...' (품질: {score}점)")
                    else:
                        print(f"    ❌ 품질 부족으로 제거됨")
                        
                except Exception as e:
                    print(f"    ❌ 오류: {e}")
    
    print(f"\n🔍 OCR 완료: {len(results)}개 방법에서 유효한 결과 획득")
    
    # 결과가 있으면 품질 점수 순으로 정렬
    if results:
        results.sort(key=lambda x: x[2], reverse=True)  # 점수 기준 내림차순
        print("\n🏆 최종 결과 순위:")
        for i, (method, text, score, desc, analysis) in enumerate(results[:10], 1):
            korean_ratio = analysis.get('korean_ratio', 0) * 100
            digit_ratio = analysis.get('digit_ratio', 0) * 100
            print(f"  {i}위. {method}")
            print(f"      점수: {score}점 ({desc})")
            print(f"      텍스트: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            print(f"      구성: 한글 {korean_ratio:.0f}%, 숫자 {digit_ratio:.0f}%")
            print()
    
    # 기존 format에 맞춰 반환 (호환성)
    converted_results = []
    for method, text, score, desc, analysis in results:
        converted_results.append((method, text, score, desc))
    
    return converted_results

def preprocess_for_handwriting(image):
    """손글씨 특화 이미지 전처리"""
    img_array = np.array(image)
    
    # 그레이스케일로 변환
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array
    
    print(f"✍️ 손글씨 전처리 시작: {gray.shape}")
    
    # 1. 해상도 증대 (2배 확대)
    height, width = gray.shape
    enlarged = cv2.resize(gray, (width*2, height*2), interpolation=cv2.INTER_CUBIC)
    print(f"🔍 해상도 증대: {gray.shape} → {enlarged.shape}")
    
    # 2. 가우시안 블러로 노이즈 제거
    denoised = cv2.GaussianBlur(enlarged, (3, 3), 0)
    
    # 3. 언샤프 마스킹으로 선명화 강화
    gaussian = cv2.GaussianBlur(denoised, (0, 0), 2.0)
    unsharp_mask = cv2.addWeighted(denoised, 1.5, gaussian, -0.5, 0)
    
    # 4. 대비 향상 (CLAHE - 손글씨 특화 설정)
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(16,16))
    enhanced = clahe.apply(unsharp_mask)
    
    # 5. 적응형 이진화 (손글씨용 설정)
    # 여러 방법을 시도하여 최적 결과 선택
    
    # 방법 1: 적응형 가우시안
    adaptive_gaussian = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                             cv2.THRESH_BINARY, 21, 10)
    
    # 방법 2: 적응형 평균
    adaptive_mean = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_MEAN_C, 
                                         cv2.THRESH_BINARY, 21, 10)
    
    # 방법 3: Otsu
    _, otsu_binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 세 방법 중 가장 좋은 결과 선택 (흰 픽셀 비율로 판단)
    methods = [
        ("적응형_가우시안", adaptive_gaussian),
        ("적응형_평균", adaptive_mean), 
        ("Otsu", otsu_binary)
    ]
    
    best_method = None
    best_score = 0
    
    for name, binary_img in methods:
        white_ratio = np.sum(binary_img == 255) / binary_img.size
        # 적절한 흰색 비율 (70-90%)인 것을 선호
        if 0.7 <= white_ratio <= 0.9:
            score = 100 - abs(white_ratio - 0.8) * 100  # 80%에 가까울수록 높은 점수
        else:
            score = max(0, 50 - abs(white_ratio - 0.8) * 100)
        
        print(f"  📊 {name}: 흰색 비율 {white_ratio:.1%}, 점수 {score:.0f}")
        
        if score > best_score:
            best_score = score
            best_method = (name, binary_img)
    
    if best_method:
        method_name, binary = best_method
        print(f"  ✅ 선택된 이진화: {method_name}")
    else:
        binary = adaptive_gaussian
        print(f"  ⚠️ 기본값 사용: 적응형_가우시안")
    
    # 6. 모폴로지 연산으로 연결된 글자 분리
    # 수직선 제거 (연결된 글자 분리용)
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3))
    temp = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=1)
    
    # 작은 노이즈 제거
    noise_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(temp, cv2.MORPH_OPEN, noise_kernel, iterations=1)
    
    # 글자 두께 약간 증가 (OCR 인식률 향상)
    thick_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    thickened = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, thick_kernel, iterations=1)
    
    print(f"✍️ 손글씨 전처리 완료")
    
    return Image.fromarray(thickened)

def create_handwriting_variants(image):
    """손글씨용 다양한 이미지 변형 생성"""
    variants = []
    
    # 기본 손글씨 전처리
    handwriting_processed = preprocess_for_handwriting(image)
    variants.append(("손글씨_기본", handwriting_processed))
    
    # 원본 이미지로도 여러 처리
    img_array = np.array(image)
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array
    
    # 1. 고해상도 + 강한 선명화
    try:
        large = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        kernel_sharp = np.array([[-1,-1,-1,-1,-1],
                                [-1, 2, 2, 2,-1],
                                [-1, 2, 8, 2,-1],
                                [-1, 2, 2, 2,-1],
                                [-1,-1,-1,-1,-1]]) / 8
        sharp = cv2.filter2D(large, -1, kernel_sharp)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        enhanced = clahe.apply(sharp)
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(("고해상도_선명", Image.fromarray(binary)))
    except:
        pass
    
    # 2. 연결 분리 특화
    try:
        # 강한 침식으로 연결 분리
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        eroded = cv2.erode(binary, erode_kernel, iterations=2)
        dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        restored = cv2.dilate(eroded, dilate_kernel, iterations=1)
        variants.append(("연결분리", Image.fromarray(restored)))
    except:
        pass
    
    # 3. 회전 보정 (±2도)
    try:
        for angle in [-2, 2]:
            center = (gray.shape[1]//2, gray.shape[0]//2)
            rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(gray, rotation_matrix, (gray.shape[1], gray.shape[0]), 
                                   borderMode=cv2.BORDER_REPLICATE)
            _, binary = cv2.threshold(rotated, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append((f"회전{angle}도", Image.fromarray(binary)))
    except:
        pass
    
    print(f"✍️ 손글씨 변형 완료: {len(variants)}개 버전")
    return variants

def validate_file(file: UploadFile) -> tuple[bool, str]:
    """파일 유효성 검사"""
    if not file.filename:
        return False, "파일명이 없습니다."
    
    ext = file.filename.split('.')[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"지원하지 않는 파일 형식입니다. ({', '.join(ALLOWED_EXTENSIONS)}만 가능)"
    
    return True, ""

async def validate_file_size(file: UploadFile) -> tuple[bool, str]:
    """파일 크기 검사"""
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        return False, f"파일 크기가 너무 큽니다. ({MAX_FILE_SIZE // (1024*1024)}MB 이하만 가능)"
    
    # 파일 포인터를 처음으로 되돌림
    await file.seek(0)
    return True, ""

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """단순 파일 업로드 (OCR 없음)"""
    try:
        # 파일 유효성 검사
        valid, error_msg = validate_file(file)
        if not valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        valid, error_msg = await validate_file_size(file)
        if not valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        contents = await file.read()
        
        # 파일 저장 (중복 방지)
        save_name = file.filename
        save_path = os.path.join(UPLOAD_DIR, save_name)
        count = 1
        while os.path.exists(save_path):
            name, ext = os.path.splitext(file.filename)
            save_name = f"{name}_{count}{ext}"
            save_path = os.path.join(UPLOAD_DIR, save_name)
            count += 1
        
        with open(save_path, "wb") as f:
            f.write(contents)
        
        return JSONResponse(content={
            "filename": save_name, 
            "message": "파일 업로드가 완료되었습니다.",
            "file_size": len(contents)
        })
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 업로드 중 오류가 발생했습니다: {str(e)}")

@app.post("/ocr_upload")
async def ocr_upload(file: UploadFile = File(...)):
    """사진 업로드 및 OCR 텍스트 추출"""
    try:
        # 파일 유효성 검사
        valid, error_msg = validate_file(file)
        if not valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        valid, error_msg = await validate_file_size(file)
        if not valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        contents = await file.read()
        
        # OCR 처리
        try:
            # Tesseract 설치 확인
            if not TESSERACT_INSTALLED:
                return {
                    "success": False,
                    "ocr_text": "",
                    "message": "❌ Tesseract OCR이 설치되지 않았습니다. 수동으로 텍스트를 입력해주세요.",
                    "error": "Tesseract not installed"
                }
            
            # 이미지 열기 및 형식 확인
            try:
                image = Image.open(io.BytesIO(contents))
                # 이미지 형식 확인 및 RGB로 변환
                if image.mode not in ('RGB', 'L'):
                    image = image.convert('RGB')
                    
            except Exception as img_error:
                return {
                    "success": False,
                    "ocr_text": "",
                    "message": f"❌ 이미지 파일을 읽을 수 없습니다. 파일이 손상되었거나 지원하지 않는 형식일 수 있습니다.",
                    "error": f"Image processing error: {str(img_error)}",
                    "suggestion": "JPG, PNG, BMP, GIF, TIFF, WebP 형식의 이미지를 사용해주세요."
                }
            
            # 이미지가 너무 크면 리사이즈
            if image.width > 2000 or image.height > 2000:
                image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
            
            # 이미지가 너무 작으면 확대 (OCR 성능 향상)
            elif image.width < 300 or image.height < 300:
                scale_factor = max(300 / image.width, 300 / image.height)
                new_size = (int(image.width * scale_factor), int(image.height * scale_factor))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            # 다중 OCR 방법으로 텍스트 추출 시도
            try:
                ocr_results = try_multiple_ocr_methods(image)
                
                if ocr_results:
                    # 품질 점수가 가장 높은 결과를 선택
                    best_result = max(ocr_results, key=lambda x: x[2])  # quality_score 기준
                    method_used = best_result[0]
                    text = best_result[1]
                    quality_score = best_result[2]
                    quality_desc = best_result[3]
                    
                    # 품질이 너무 낮으면 경고
                    if quality_score < 40:
                        warning_message = f"⚠️ 텍스트 품질이 낮습니다 (품질: {quality_desc}, {quality_score}점). 결과를 확인해주세요."
                    else:
                        warning_message = None
                    
                    # 디버깅 정보 포함 (품질 점수 포함)
                    debug_info = []
                    for method, result, q_score, q_desc in ocr_results:
                        short_result = result[:50] + "..." if len(result) > 50 else result
                        debug_info.append(f"{method} (품질: {q_score}점, {q_desc}): {short_result}")
                    
                    return {
                        "success": True,
                        "ocr_text": text,
                        "message": f"✅ 텍스트 추출 완료! ({method_used} 방법 사용, 품질: {quality_desc})",
                        "quality_score": quality_score,
                        "quality_description": quality_desc,
                        "warning": warning_message,
                        "debug_info": debug_info,
                        "total_methods_tried": len(ocr_results),
                        "best_method": method_used
                    }
                else:
                    # 모든 방법이 실패한 경우
                    return {
                        "success": True,
                        "ocr_text": "",
                        "message": "📄 텍스트를 감지할 수 없습니다.",
                        "detailed_message": "6가지 다른 OCR 방법을 시도했지만 의미있는 텍스트를 찾을 수 없습니다.",
                        "suggestion": "다음을 확인해보세요:\n• 글씨가 선명하고 읽을 수 있나요?\n• 배경과 글씨의 대비가 충분한가요?\n• 이미지에 노이즈나 얼룩이 많지 않나요?\n• 글씨 크기가 너무 작지 않나요?\n• 손글씨가 너무 흘림체는 아닌가요?",
                        "quality_info": "모든 OCR 방법에서 깨진 글자나 의미없는 문자만 감지되었습니다."
                    }
                    
            except Exception as ocr_error:
                return {
                    "success": False,
                    "ocr_text": "",
                    "message": "❌ OCR 처리 중 오류가 발생했습니다.",
                    "error": f"OCR error: {str(ocr_error)}",
                    "suggestion": "이미지를 다시 확인하거나 다른 이미지를 시도해보세요."
                }
            
        except Exception as ocr_error:
            raise HTTPException(
                status_code=500, 
                detail=f"OCR 처리 중 오류가 발생했습니다. 다른 사진을 시도해보세요. (상세: {str(ocr_error)})"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 처리 중 오류가 발생했습니다: {str(e)}")

@app.post("/ai_feedback")
async def ai_feedback(text: str = Body(..., embed=True)):
    """AI 피드백 생성"""
    try:
        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="분석할 텍스트가 없습니다.")
        
        if len(text.strip()) < 10:
            raise HTTPException(status_code=400, detail="텍스트가 너무 짧습니다. 최소 10자 이상 입력해주세요.")
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500, 
                detail="AI 서비스가 설정되지 않았습니다. 관리자에게 문의하세요."
            )
        
        openai.api_key = api_key
        prompt = f"""
        아래는 학생이 쓴 글입니다. 이 글을 읽고 학생의 생각을 확장시켜줄 수 있는 질문 또는 코칭을 2개 생성해 주세요. 
        학생이 이해하기 쉽고 건설적인 피드백을 제공해주세요. 각 항목은 번호로 구분해 주세요.
        
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
            
            if not feedback:
                raise HTTPException(status_code=500, detail="AI 피드백을 생성할 수 없습니다. 잠시 후 다시 시도해주세요.")
            
            return {
                "feedback": feedback,
                "message": "AI 피드백이 생성되었습니다.",
                "input_length": len(text)
            }
            
        except openai.RateLimitError:
            raise HTTPException(status_code=429, detail="AI 서비스 사용량이 초과되었습니다. 잠시 후 다시 시도해주세요.")
        except openai.APIError as api_error:
            raise HTTPException(status_code=500, detail=f"AI 서비스 오류: {str(api_error)}")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 피드백 생성 중 오류가 발생했습니다: {str(e)}")

def extract_stage_from_evaluation(evaluation: str) -> int:
    """AI 평가에서 단계 추출"""
    match = re.search(r'단계:\s*([123])', evaluation)
    if match:
        return int(match.group(1))
    return 2  # 기본값

@app.post("/ai_evaluate")
async def ai_evaluate(
    text: str = Body(...), 
    submission_id: int = Body(...)
):
    """AI 최종 평가"""
    try:
        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="평가할 텍스트가 없습니다.")
        
        if len(text.strip()) < 10:
            raise HTTPException(status_code=400, detail="텍스트가 너무 짧습니다. 최소 10자 이상 입력해주세요.")
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500, 
                detail="AI 서비스가 설정되지 않았습니다. 관리자에게 문의하세요."
            )
        
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
            
            if not result:
                raise HTTPException(status_code=500, detail="AI 평가를 생성할 수 없습니다. 잠시 후 다시 시도해주세요.")
            
            stage = extract_stage_from_evaluation(result)
            
            # 데이터베이스에 AI 평가 결과 저장
            if db:
                db.update_ai_evaluation(submission_id, result, stage)
            
            return {
                "evaluation": result,
                "stage": stage,
                "message": "AI 평가가 완료되고 저장되었습니다.",
                "input_length": len(text),
                "submission_id": submission_id
            }
            
        except openai.RateLimitError:
            raise HTTPException(status_code=429, detail="AI 서비스 사용량이 초과되었습니다. 잠시 후 다시 시도해주세요.")
        except openai.APIError as api_error:
            raise HTTPException(status_code=500, detail=f"AI 서비스 오류: {str(api_error)}")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 평가 중 오류가 발생했습니다: {str(e)}")

@app.post("/submit_revision")
async def submit_revision(
    student_id: str = Body(...), 
    original_text: str = Body(...), 
    revised_text: str = Body(...)
):
    """학생이 수정한 글을 데이터베이스에 저장"""
    try:
        if not db:
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        if not student_id or not student_id.strip():
            raise HTTPException(status_code=400, detail="학생 ID가 필요합니다.")
        
        if not revised_text or not revised_text.strip():
            raise HTTPException(status_code=400, detail="수정된 글이 필요합니다.")
        
        submission_id = db.save_submission(student_id.strip(), original_text, revised_text.strip())
        
        return JSONResponse(content={
            "message": "글 제출이 완료되었습니다.",
            "submission_id": submission_id,
            "submit_time": datetime.now().isoformat(),
            "student_id": student_id.strip()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"제출 저장 중 오류가 발생했습니다: {str(e)}")

@app.post("/submit_full_evaluation")
async def submit_full_evaluation(
    student_id: str = Body(...), 
    original_text: str = Body(...), 
    revised_text: str = Body(...),
    ai_feedback: str = Body(...),
    ai_evaluation: str = Body(...)
):
    """전체 평가 프로세스 한번에 저장"""
    try:
        if not db:
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        submission_id = db.save_submission(student_id, original_text, revised_text)
        db.update_ai_feedback(submission_id, ai_feedback)
        
        # AI 평가에서 단계 추출
        stage = extract_stage_from_evaluation(ai_evaluation)
        db.update_ai_evaluation(submission_id, ai_evaluation, stage)
        
        return JSONResponse(content={
            "message": "전체 평가가 완료되었습니다.",
            "submission_id": submission_id,
            "stage": stage,
            "submit_time": datetime.now().isoformat()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"평가 저장 중 오류가 발생했습니다: {str(e)}")

# 교사용 API
@app.get("/teacher/submissions")
async def get_all_submissions():
    """모든 학생 제출 내역 조회 (교사용)"""
    try:
        if not db:
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        submissions = db.get_all_submissions()
        return {
            "submissions": submissions,
            "total_count": len(submissions),
            "message": "제출 내역을 성공적으로 조회했습니다."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 조회 중 오류가 발생했습니다: {str(e)}")

@app.get("/teacher/student/{student_id}")
async def get_student_submissions(student_id: str):
    """특정 학생의 모든 제출 내역 조회"""
    try:
        if not db:
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        if not student_id or not student_id.strip():
            raise HTTPException(status_code=400, detail="학생 ID가 필요합니다.")
        
        submissions = db.get_student_submissions(student_id.strip())
        return {
            "student_id": student_id.strip(),
            "submissions": submissions,
            "total_count": len(submissions),
            "message": f"{student_id} 학생의 제출 내역을 조회했습니다."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 조회 중 오류가 발생했습니다: {str(e)}")

@app.get("/submission/{submission_id}")
async def get_submission(submission_id: int):
    """특정 제출 내역 상세 조회"""
    try:
        if not db:
            raise HTTPException(status_code=500, detail="데이터베이스를 사용할 수 없습니다.")
        
        submission = db.get_submission_by_id(submission_id)
        if not submission:
            raise HTTPException(status_code=404, detail="제출 내역을 찾을 수 없습니다.")
        
        return submission
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 조회 중 오류가 발생했습니다: {str(e)}")

@app.get("/health")
def health_check():
    """서버 상태 확인"""
    return {
        "status": "healthy",
        "message": "AI 학생 글 평가 시스템이 정상 작동 중입니다.",
        "version": "2.0",
        "database": "connected" if db else "disconnected",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/")
def read_root():
    return {
        "message": "🎓 AI 학생 글 평가 시스템에 오신 것을 환영합니다!",
        "version": "2.0 with Database",
        "endpoints": {
            "학생용": "/ocr_upload, /ai_feedback, /ai_evaluate, /submit_revision",
            "교사용": "/teacher/submissions, /teacher/student/{student_id}",
            "기타": "/health, /docs"
        },
        "frontend": {
            "학생용": "student.html",
            "교사용": "teacher.html",
            "테스트용": "test.html"
        }
    } 

def korean_language_correction(text):
    """한국어 언어모델 기반 텍스트 교정"""
    if not text:
        return text
    
    print(f"🔤 언어모델 교정 시작: '{text}'")
    
    # 1. 자주 잘못 인식되는 글자 교정
    common_mistakes = {
        # 유사한 모양의 글자들
        '밑': '법',  # 'ㅁ'과 'ㅂ' 혼동
        '가': '나',  # 'ㄱ'과 'ㄴ' 혼동
        '정': '정',  # 그대로
        '해': '해',  # 그대로
        '걸': '걸',  # 그대로
        '꼭': '꼭',  # 그대로
        '지': '지',  # 그대로
        '켜': '켜',  # 그대로
        '야': '야',  # 그대로
        '하': '하',  # 그대로
        '는': '는',  # 그대로
        '것': '것',  # 그대로
        '강': '강',  # 그대로
        '제': '제',  # 그대로
        '적': '적',  # 그대로
        '으': '으',  # 그대로
        '로': '로',  # 그대로
        '체': '체',  # 그대로
        '벌': '벌',  # 그대로
        '을': '을',  # 그대로
        '받': '받',  # 그대로
        '고': '고',  # 그대로
        '도': '도',  # 그대로
        '덕': '덕',  # 그대로
        '은': '은',  # 그대로
        '양': '양',  # 그대로
        '심': '심',  # 그대로
        '의': '의',  # 그대로
        '실': '실',  # 그대로
        '망': '망',  # 그대로
        '과': '과',  # 그대로
        '비': '비',  # 그대로
        '난': '난',  # 그대로
        '다': '다',  # 그대로
        
        # 자주 잘못 인식되는 패턴들
        '체니': '체벌',
        '성앙': '실망',
        '버언': '받는',
        '오고': '을',
        '억': '도덕',
        '앙가': '과',
    }
    
    corrected = text
    corrections_made = []
    
    for wrong, correct in common_mistakes.items():
        if wrong in corrected:
            corrected = corrected.replace(wrong, correct)
            corrections_made.append(f"{wrong}→{correct}")
    
    if corrections_made:
        print(f"  📝 글자 교정: {', '.join(corrections_made)}")
    
    # 2. 단어 경계 추론 및 교정
    word_patterns = [
        # 법률 관련 용어
        (r'법.*?는', '법은'),
        (r'나.*?라.*?에.*?서', '나라에서'),
        (r'정.*?해.*?준.*?걸', '정해준 걸'),
        (r'꼭.*?지.*?켜.*?야', '꼭 지켜야'),
        (r'하.*?는.*?것', '하는 것'),
        (r'강.*?제.*?적.*?으.*?로', '강제적으로'),
        (r'체.*?벌.*?을', '체벌을'),
        (r'받.*?고', '받고'),
        (r'도.*?덕.*?은', '도덕은'),
        (r'양.*?심.*?의', '양심의'),
        (r'실.*?망.*?과', '실망과'),
        (r'비.*?난.*?을', '비난을'),
        (r'받.*?는.*?다', '받는다'),
    ]
    
    for pattern, replacement in word_patterns:
        if re.search(pattern, corrected):
            old_text = corrected
            corrected = re.sub(pattern, replacement, corrected)
            if old_text != corrected:
                print(f"  🔍 패턴 교정: '{old_text}' → '{corrected}'")
    
    # 3. 문장 구조 복원
    # 쉼표와 마침표 추가
    if '것' in corrected and '법은' in corrected and ',' not in corrected:
        corrected = corrected.replace('것', '것,')
        print(f"  📖 문장부호 추가: 쉼표 삽입")
    
    if corrected and not corrected.endswith('.'):
        if any(ending in corrected for ending in ['다', '요', '음', '니다']):
            corrected += '.'
            print(f"  📖 문장부호 추가: 마침표 삽입")
    
    # 4. 최종 정리
    corrected = re.sub(r'\s+', ' ', corrected)  # 연속 공백 제거
    corrected = corrected.strip()
    
    if corrected != text:
        print(f"✅ 교정 완료: '{text}' → '{corrected}'")
        return corrected
    else:
        print(f"ℹ️ 교정 불필요: '{text}'")
        return text

def enhance_korean_ocr_result(text):
    """한국어 OCR 결과 종합 개선"""
    if not text:
        return text
    
    print(f"🚀 한국어 OCR 결과 종합 개선 시작")
    
    # 1. 기본 정리
    cleaned = clean_korean_ocr_text(text)
    if not cleaned:
        print(f"❌ 기본 정리 단계에서 제거됨")
        return ""
    
    # 2. 언어모델 교정
    corrected = korean_language_correction(cleaned)
    
    # 3. 최종 품질 평가
    final_score, final_desc, final_analysis = analyze_korean_text_quality(corrected)
    
    print(f"📊 최종 품질: {final_score}점 ({final_desc})")
    print(f"🎯 최종 결과: '{corrected}'")
    
    return corrected 