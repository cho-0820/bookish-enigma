import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional

class DatabaseManager:
    def __init__(self, db_path: str = "student_submissions.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """row_factory가 설정된 데이터베이스 연결을 반환합니다."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
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
        
        # 새로운 평가 기준 테이블 추가
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS evaluation_criteria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        print("✅ 데이터베이스 테이블 초기화 완료")
    
    def save_submission(self, student_id: str, ocr_text: str = None, revised_text: str = None, ai_stage: int = 1) -> int:
        """제출 내역 저장 (유연한 파라미터 버전)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO submissions (student_id, ocr_text, revised_text, ai_stage, submit_time)
        VALUES (?, ?, ?, ?, ?)
        ''', (student_id, ocr_text, revised_text, ai_stage, datetime.now()))
        
        submission_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return submission_id
    
    def update_ai_feedback(self, submission_id: int, ai_feedback: str):
        """AI 피드백 업데이트"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE submissions 
        SET ai_feedback = ?, ai_stage = 2, update_time = ?
        WHERE id = ?
        ''', (ai_feedback, datetime.now(), submission_id))
        
        conn.commit()
        conn.close()
    
    def update_ai_evaluation(self, submission_id: int, ai_evaluation: str, ai_stage: int = 3):
        """AI 최종 평가 업데이트"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE submissions 
        SET ai_evaluation = ?, ai_stage = ?, update_time = ?
        WHERE id = ?
        ''', (ai_evaluation, ai_stage, datetime.now(), submission_id))
        
        conn.commit()
        conn.close()
    
    def get_all_submissions(self):
        """모든 제출 내역 조회"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM submissions ORDER BY submit_time DESC")
        rows = cursor.fetchall()
        conn.close()
        
        # Row 객체를 딕셔너리로 변환
        return [dict(row) for row in rows]
    
    def get_submission_by_id(self, submission_id: int):
        """ID로 특정 제출 내역 조회"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None

    # === 평가 기준 관련 메서드들 ===

    def save_criteria(self, title, description):
        """새로운 평가 기준을 저장합니다."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO evaluation_criteria (title, description, created_at) VALUES (?, ?, ?)",
                (title, description, datetime.now())
            )
            criteria_id = cursor.lastrowid
            conn.commit()
            conn.close()
            print(f"✅ 평가 기준 저장 완료: ID={criteria_id}, 제목={title}")
            return criteria_id
        except Exception as e:
            print(f"❌ 평가 기준 저장 오류: {e}")
            raise e

    def get_all_criteria(self):
        """모든 평가 기준을 조회합니다."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, description, created_at FROM evaluation_criteria ORDER BY created_at DESC")
            rows = cursor.fetchall()
            conn.close()
            
            # Row 객체를 딕셔너리로 변환
            criteria_list = []
            for row in rows:
                criteria_list.append({
                    'id': row['id'],
                    'title': row['title'],
                    'description': row['description'],
                    'created_at': row['created_at']
                })
            
            print(f"✅ 평가 기준 조회 완료: {len(criteria_list)}개")
            return criteria_list
        except Exception as e:
            print(f"❌ 평가 기준 조회 오류: {e}")
            return []

    def get_criteria_by_id(self, criteria_id):
        """ID로 특정 평가 기준을 조회합니다."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, description, created_at FROM evaluation_criteria WHERE id=?", (criteria_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'id': row['id'],
                    'title': row['title'],
                    'description': row['description'],
                    'created_at': row['created_at']
                }
            return None
        except Exception as e:
            print(f"❌ 평가 기준 조회 오류: {e}")
            return None

    def delete_criteria(self, criteria_id):
        """평가 기준을 삭제합니다."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM evaluation_criteria WHERE id=?", (criteria_id,))
            conn.commit()
            conn.close()
            print(f"✅ 평가 기준 삭제 완료: ID={criteria_id}")
        except Exception as e:
            print(f"❌ 평가 기준 삭제 오류: {e}")
            raise e

    def update_criteria(self, criteria_id, title, description):
        """평가 기준을 수정합니다."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE evaluation_criteria SET title=?, description=? WHERE id=?",
                (title, description, criteria_id)
            )
            conn.commit()
            conn.close()
            print(f"✅ 평가 기준 수정 완료: ID={criteria_id}, 제목={title}")
        except Exception as e:
            print(f"❌ 평가 기준 수정 오류: {e}")
            raise e 