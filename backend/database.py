import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional

class DatabaseManager:
    def __init__(self, db_path: str = "student_submissions.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """데이터베이스 테이블 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 학생 제출 내역 테이블
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            original_image_path TEXT,
            ocr_text TEXT,
            ai_feedback TEXT,
            revised_text TEXT,
            ai_evaluation TEXT,
            ai_stage INTEGER,
            submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_submission(self, student_id: str, original_text: str, revised_text: str) -> int:
        """2차 제출 저장"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO submissions (student_id, ocr_text, revised_text, submit_time)
        VALUES (?, ?, ?, ?)
        ''', (student_id, original_text, revised_text, datetime.now().isoformat()))
        
        submission_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return submission_id
    
    def update_ai_feedback(self, submission_id: int, ai_feedback: str):
        """AI 피드백 업데이트"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE submissions SET ai_feedback = ?, update_time = ?
        WHERE id = ?
        ''', (ai_feedback, datetime.now().isoformat(), submission_id))
        
        conn.commit()
        conn.close()
    
    def update_ai_evaluation(self, submission_id: int, ai_evaluation: str, ai_stage: int):
        """AI 평가 결과 업데이트"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE submissions SET ai_evaluation = ?, ai_stage = ?, update_time = ?
        WHERE id = ?
        ''', (ai_evaluation, ai_stage, datetime.now().isoformat(), submission_id))
        
        conn.commit()
        conn.close()
    
    def get_student_submissions(self, student_id: str) -> List[Dict]:
        """학생별 제출 내역 조회"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM submissions WHERE student_id = ?
        ORDER BY submit_time DESC
        ''', (student_id,))
        
        columns = [description[0] for description in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        conn.close()
        return results
    
    def get_all_submissions(self) -> List[Dict]:
        """모든 제출 내역 조회 (교사용)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM submissions
        ORDER BY submit_time DESC
        ''')
        
        columns = [description[0] for description in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        conn.close()
        return results
    
    def get_submission_by_id(self, submission_id: int) -> Optional[Dict]:
        """ID로 특정 제출 조회"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM submissions WHERE id = ?
        ''', (submission_id,))
        
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            result = dict(zip(columns, row))
        else:
            result = None
        
        conn.close()
        return result 