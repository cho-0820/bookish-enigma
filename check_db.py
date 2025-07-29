#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import os

def check_database():
    """기존 데이터베이스 파일 확인"""
    
    db_path = "backend/student_submissions.db"
    
    if not os.path.exists(db_path):
        print(f"❌ 데이터베이스 파일을 찾을 수 없습니다: {db_path}")
        return
    
    print(f"🔍 데이터베이스 파일 확인: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. 테이블 목록 확인
        print("\n📋 테이블 목록:")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        for table in tables:
            print(f"  - {table[0]}")
        
        # 2. evaluation_criteria 테이블 구조 확인
        print("\n🏗️ evaluation_criteria 테이블 구조:")
        try:
            cursor.execute("PRAGMA table_info(evaluation_criteria)")
            columns = cursor.fetchall()
            if columns:
                for col in columns:
                    print(f"  - {col[1]} ({col[2]})")
            else:
                print("  ❌ evaluation_criteria 테이블이 존재하지 않습니다.")
        except sqlite3.OperationalError as e:
            print(f"  ❌ 테이블 구조 확인 실패: {e}")
        
        # 3. evaluation_criteria 데이터 확인
        print("\n📊 evaluation_criteria 데이터:")
        try:
            cursor.execute("SELECT COUNT(*) FROM evaluation_criteria")
            count = cursor.fetchone()[0]
            print(f"  총 {count}개의 평가 기준")
            
            if count > 0:
                cursor.execute("SELECT id, title, description, created_at FROM evaluation_criteria ORDER BY id")
                rows = cursor.fetchall()
                for row in rows:
                    print(f"  - ID: {row[0]}, 제목: {row[1]}, 설명: {row[2][:50]}...")
        except sqlite3.OperationalError as e:
            print(f"  ❌ 데이터 조회 실패: {e}")
        
        # 4. submissions 테이블 확인
        print("\n📝 submissions 테이블:")
        try:
            cursor.execute("SELECT COUNT(*) FROM submissions")
            count = cursor.fetchone()[0]
            print(f"  총 {count}개의 제출물")
        except sqlite3.OperationalError as e:
            print(f"  ❌ submissions 테이블 확인 실패: {e}")
        
        conn.close()
        print("\n✅ 데이터베이스 확인 완료")
        
    except Exception as e:
        print(f"❌ 데이터베이스 확인 중 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_database() 