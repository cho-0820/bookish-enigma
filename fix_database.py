#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import os

def fix_database():
    """데이터베이스 스키마 수정 및 평가 기준 테이블 생성"""
    
    db_path = "backend/student_submissions.db"
    
    print(f"🔧 데이터베이스 수정 시작: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. evaluation_criteria 테이블 강제 생성
        print("\n📋 evaluation_criteria 테이블 생성...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS evaluation_criteria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 2. 테스트 데이터 추가
        print("\n📝 테스트 평가 기준 추가...")
        test_criteria = [
            ("창의성", "학생의 독창적이고 참신한 아이디어를 평가합니다."),
            ("논리성", "글의 논리적 구성과 체계적인 전개를 평가합니다."),
            ("표현력", "명확하고 적절한 언어 표현을 평가합니다.")
        ]
        
        for title, description in test_criteria:
            cursor.execute(
                "INSERT INTO evaluation_criteria (title, description) VALUES (?, ?)",
                (title, description)
            )
        
        conn.commit()
        
        # 3. 결과 확인
        print("\n✅ 생성된 평가 기준 확인:")
        cursor.execute("SELECT id, title, description FROM evaluation_criteria ORDER BY id")
        rows = cursor.fetchall()
        for row in rows:
            print(f"  - ID: {row[0]}, 제목: {row[1]}, 설명: {row[2]}")
        
        conn.close()
        print("\n🎉 데이터베이스 수정 완료!")
        
    except Exception as e:
        print(f"❌ 데이터베이스 수정 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fix_database() 