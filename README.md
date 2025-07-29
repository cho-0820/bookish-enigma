# 🎓 AI 학생 글 평가 시스템

인공지능을 활용한 스마트한 글쓰기 학습 플랫폼

## 📋 프로젝트 개요

학생들의 손글씨 사진을 AI가 인식하고, 맞춤형 피드백을 제공하여 글쓰기 능력을 향상시키는 교육용 시스템입니다.

### 주요 기능
- 📷 **손글씨 OCR 인식**: 사진에서 텍스트 자동 추출
- 🤖 **AI 맞춤형 피드백**: GPT 기반 개인화된 코칭 제공
- 📊 **단계별 평가**: 루브릭 기준 자동 평가 시스템
- 👨‍🏫 **교사 대시보드**: 학생 진도 및 결과 통합 관리
- 💾 **데이터 관리**: SQLite 기반 안전한 제출 내역 저장

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 가상환경 생성 및 활성화
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux

# 필요한 패키지 설치
pip install fastapi uvicorn python-multipart
pip install pillow pytesseract openai
```

### 2. OpenAI API 키 설정

```bash
# Windows
set OPENAI_API_KEY=your_api_key_here

# Mac/Linux
export OPENAI_API_KEY=your_api_key_here
```

### 3. 서버 실행

```bash
cd backend
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 4. 웹 브라우저에서 접속

- **메인 페이지**: http://127.0.0.1:8000 또는 `index.html`
- **학생용**: `student.html`
- **교사용**: `teacher.html`
- **API 문서**: http://127.0.0.1:8000/docs

## 🎯 사용 방법

### 학생용 플로우
1. **학생 ID 입력** - 본인 식별용 ID 입력
2. **사진 업로드** - 글이 적힌 사진 업로드 (JPG, PNG, 10MB 이하)
3. **OCR 확인** - 자동 추출된 텍스트 확인 및 수정
4. **AI 피드백** - 맞춤형 질문/코칭 받기
5. **글 수정** - 피드백을 참고하여 글 개선
6. **제출** - 수정된 글 제출
7. **최종 평가** - AI의 단계별 평가 확인

### 교사용 기능
- **전체 현황** - 모든 학생 제출 통계
- **개별 조회** - 학생별 상세 진도 확인
- **데이터 내보내기** - CSV 형태로 결과 다운로드
- **실시간 모니터링** - 실시간 제출 현황 추적

## 🗂️ 프로젝트 구조

```
cursor/
├── backend/
│   ├── main.py              # FastAPI 메인 서버
│   ├── database.py          # SQLite 데이터베이스 관리
│   ├── uploads/             # 업로드된 파일 저장소
│   └── student_submissions.db # 제출 내역 데이터베이스
├── index.html               # 메인 랜딩 페이지
├── student.html             # 학생용 인터페이스
├── teacher.html             # 교사용 대시보드
├── test.html               # 개발자용 테스트 페이지
└── README.md               # 프로젝트 문서
```

## 🛠️ 기술 스택

### 백엔드
- **FastAPI**: 고성능 웹 API 프레임워크
- **SQLite**: 경량 데이터베이스
- **OpenAI GPT**: AI 피드백 및 평가
- **Tesseract OCR**: 손글씨 텍스트 인식
- **Pillow**: 이미지 처리

### 프론트엔드
- **HTML5/CSS3**: 반응형 웹 디자인
- **JavaScript**: 비동기 API 통신
- **Progressive Enhancement**: 점진적 기능 향상

## 📊 API 엔드포인트

### 학생용 API
- `POST /ocr_upload` - 사진 업로드 및 OCR
- `POST /ai_feedback` - AI 피드백 생성
- `POST /ai_evaluate` - AI 최종 평가
- `POST /submit_revision` - 수정된 글 제출

### 교사용 API
- `GET /teacher/submissions` - 전체 제출 내역
- `GET /teacher/student/{student_id}` - 학생별 내역
- `GET /submission/{submission_id}` - 상세 조회

### 시스템 API
- `GET /health` - 서버 상태 확인
- `GET /docs` - API 문서 (Swagger)

## 🔧 설정 및 커스터마이징

### OCR 언어 설정
```python
# backend/main.py에서 수정
text = pytesseract.image_to_string(image, lang='kor+eng')
```

### AI 프롬프트 수정
```python
# main.py의 ai_feedback, ai_evaluate 함수에서 prompt 변수 수정
```

### 파일 업로드 제한
```python
# main.py에서 수정
ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
```

## 🚨 문제 해결

### 일반적인 오류

1. **OCR이 인식하지 못하는 경우**
   - 더 선명한 사진 촬영
   - 조명이 좋은 환경에서 촬영
   - 글씨가 명확하게 보이도록 촬영

2. **AI API 오류**
   - OpenAI API 키 확인
   - 네트워크 연결 상태 확인
   - API 사용량 한도 확인

3. **서버 연결 오류**
   - 백엔드 서버 실행 상태 확인
   - 포트 번호 일치 여부 확인 (8000)

### 로그 확인
```bash
# 서버 로그에서 오류 확인
python -m uvicorn main:app --reload --log-level debug
```

## 🤝 기여하기

1. 이슈 리포트 및 기능 제안
2. 코드 개선 및 버그 수정
3. 문서화 개선
4. 테스트 케이스 추가

## 📄 라이선스

교육 목적으로 자유롭게 사용 가능합니다.

## 🙋‍♂️ 지원

질문이나 문제가 있으시면 이슈를 등록해 주세요.

---

**✨ AI와 함께하는 스마트한 글쓰기 학습을 시작하세요!** 