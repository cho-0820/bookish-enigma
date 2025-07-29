#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from database import DatabaseManager

def test_database():
    """데이터베이스 연결 및 평가 기준 기능 테스트"""
    
    print("🔧 데이터베이스 테스트 시작...")
    
    try:
        # 데이터베이스 초기화
        db = DatabaseManager("test_db.db")  # 테스트용 별도 DB
        print("✅ 데이터베이스 초기화 성공")
        
        # 1. 평가 기준 저장 테스트
        print("\n📝 평가 기준 저장 테스트...")
        criteria_id = db.save_criteria("창의성", "학생의 독창적이고 참신한 아이디어를 평가합니다.")
        print(f"저장된 평가 기준 ID: {criteria_id}")
        
        # 2. 평가 기준 조회 테스트
        print("\n📋 평가 기준 조회 테스트...")
        criteria_list = db.get_all_criteria()
        print(f"조회된 평가 기준 수: {len(criteria_list)}")
        for criterion in criteria_list:
            print(f"  - ID: {criterion['id']}, 제목: {criterion['title']}")
        
        # 3. 추가 평가 기준 저장
        print("\n📝 추가 평가 기준 저장...")
        db.save_criteria("논리성", "글의 논리적 구성과 체계성을 평가합니다.")
        db.save_criteria("문법 정확도", "맞춤법, 띄어쓰기, 문법의 정확성을 평가합니다.")
        
        # 4. 전체 조회
        print("\n📋 전체 평가 기준 조회...")
        all_criteria = db.get_all_criteria()
        print(f"총 {len(all_criteria)}개의 평가 기준:")
        for criterion in all_criteria:
            print(f"  - {criterion['title']}: {criterion['description']}")
        
        print("\n✅ 모든 데이터베이스 테스트 완료!")
        
    except Exception as e:
        print(f"❌ 데이터베이스 테스트 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_database() 