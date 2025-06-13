#!/usr/bin/env python3
"""
뉴스 토픽 분석 MCP 서버 (FastMCP 기반)
daily_news_analyzer.py로 수집된 뉴스 데이터를 검색하고 분석하는 MCP 서버
"""

import asyncio
import json
import sys
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import pymysql
from mcp.server.fastmcp import FastMCP # FastMCP 임포트
from mcp.types import TextContent, Tool, CallToolResult # 필요한 타입만 임포트

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)  # stderr로 로그 출력
    ]
)
logger = logging.getLogger(__name__)

# MySQL 연결 설정 (daily_news_analyzer.py와 동일하게 설정)
MYSQL_HOST = "localhost"
MYSQL_USER = "root"
MYSQL_PASSWORD = "mysql@24!"
MYSQL_DB = "news_analysis_db"

# FastMCP 서버 인스턴스 생성
# FastMCP는 내부적으로 Server를 관리하며, initialize 핸들러는 자동으로 처리됩니다.
mcp_server = FastMCP("news-topic-analyzer")
logger.info("FastMCP 서버 인스턴스 생성 완료: news-topic-analyzer")

class DatabaseManager:
    """데이터베이스 연결 및 쿼리 실행을 관리하는 클래스"""
    def __init__(self):
        logger.info("DatabaseManager 초기화 중...")

    def get_db_connection(self):
        """데이터베이스 연결을 반환합니다."""
        try:
            logger.debug("데이터베이스 연결 시도...")
            connection = pymysql.connect(
                host=MYSQL_HOST,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                db=MYSQL_DB,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10  # 연결 타임아웃 설정
            )
            logger.debug("데이터베이스 연결 성공")
            return connection
        except pymysql.Error as e:
            logger.error(f"데이터베이스 연결 실패: {e}")
            raise Exception(f"데이터베이스 연결 실패: {e}")

    async def test_db_connection(self):
        """데이터베이스 연결을 테스트합니다."""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            conn.close()
            logger.info("데이터베이스 연결 테스트 성공")
            return True
        except Exception as e:
            logger.error(f"데이터베이스 연결 테스트 실패: {e}")
            return False

# DatabaseManager 인스턴스 생성
db_manager = DatabaseManager()

@mcp_server.tool()
async def get_available_analysis_dates() -> str:
    """
    데이터베이스에 저장된 뉴스 기사 분석이 완료된 날짜 목록을 조회합니다.
    최근 30일간의 데이터를 반환합니다.
    """
    logger.info("get_available_analysis_dates 도구 호출")
    conn = None
    try:
        conn = db_manager.get_db_connection()
        cursor = conn.cursor()
        query = """
        SELECT DISTINCT DATE(analysis_date) as analysis_date 
        FROM news_articles 
        ORDER BY analysis_date DESC 
        LIMIT 30
        """
        cursor.execute(query)
        results = cursor.fetchall()
        dates = [str(row['analysis_date']) for row in results]
        logger.info(f"분석 가능한 날짜 {len(dates)}개 조회 완료")
        
        return json.dumps({
            "available_dates": dates,
            "total_count": len(dates)
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"get_available_analysis_dates 도구 실행 중 오류: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)
    finally:
        if conn:
            conn.close()

@mcp_server.tool()
async def get_news_analysis_data(
    start_date: str, 
    end_date: str, 
    keyword: Optional[str] = None, 
    topic_id: Optional[int] = None
) -> str:
    """
    지정된 기간 동안의 뉴스 기사 분석 데이터를 검색합니다.
    키워드나 토픽 ID로 필터링하여 특정 주제의 기사를 찾거나, 전체 뉴스를 조회할 수 있습니다.
    예를 들어 '오늘의 IT 뉴스', '2024년 5월 1일부터 10일까지의 반도체 관련 뉴스'와 같은 질문에 사용합니다.
    
    Args:
        start_date (str): 검색 시작 날짜 (YYYY-MM-DD 형식, 예: 2024-01-01). 필수 항목입니다.
        end_date (str): 검색 종료 날짜 (YYYY-MM-DD 형식, 예: 2024-01-31). 필수 항목입니다.
        keyword (str, optional): 제목, 설명, 처리된 텍스트에서 검색할 키워드 (선택 사항). 예: '인공지능', '반도체'.
        topic_id (int, optional): 특정 토픽 ID로 필터링 (선택 사항). `get_topic_keyword_frequency`나 `get_topic_trends`를 통해 얻은 토픽 ID를 사용할 수 있습니다.
    
    Returns:
        str: JSON 형식의 뉴스 분석 데이터 목록
    """
    logger.info(f"get_news_analysis_data 도구 호출: {start_date} ~ {end_date}, 키워드: {keyword}, 토픽 ID: {topic_id}")
    conn = None
    try:
        conn = db_manager.get_db_connection()
        cursor = conn.cursor()
        
        base_query = """
        SELECT 
            na.id,
            na.title,
            na.link,
            na.description,
            na.pub_date,
            na.original_text,
            na.processed_text,
            na.analysis_date,
            tr.topic_id,
            tr.probability,
            ti.topic_name,
            ti.representation
        FROM news_articles na
        LEFT JOIN topic_results tr ON na.id = tr.article_id
        LEFT JOIN topic_info ti ON tr.topic_id = ti.topic_id AND DATE(tr.analysis_date) = DATE(ti.analysis_date)
        WHERE DATE(na.analysis_date) BETWEEN %s AND %s
        """
        
        params = [start_date, end_date]
        
        if keyword:
            base_query += " AND (na.title LIKE %s OR na.description LIKE %s OR na.processed_text LIKE %s)"
            keyword_pattern = f"%{keyword}%"
            params.extend([keyword_pattern, keyword_pattern, keyword_pattern])
        
        if topic_id is not None:
            base_query += " AND tr.topic_id = %s"
            params.append(topic_id)
        
        base_query += " ORDER BY na.pub_date DESC LIMIT 100" # 결과 너무 많아지는 것 방지
        
        cursor.execute(base_query, params)
        results = cursor.fetchall()
        
        processed_results = []
        for row in results:
            processed_row = {}
            for key, value in row.items():
                if isinstance(value, datetime):
                    processed_row[key] = value.isoformat()
                else:
                    processed_row[key] = value
            processed_results.append(processed_row)
        
        logger.info(f"뉴스 분석 데이터 {len(processed_results)}건 조회 완료")
        return json.dumps({
            "period": f"{start_date} ~ {end_date}",
            "total_articles": len(processed_results),
            "keyword_filter": keyword,
            "topic_id_filter": topic_id,
            "articles": processed_results
        }, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.error(f"get_news_analysis_data 도구 실행 중 오류: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)
    finally:
        if conn:
            conn.close()

@mcp_server.tool()
async def get_topic_keyword_frequency(
    analysis_date: str, 
    topic_id: int
) -> str:
    """
    특정 날짜의 특정 토픽 ID에 대한 주요 키워드와 그 빈도 정보를 반환합니다.
    해당 토픽이 어떤 내용에 집중하고 있는지 파악하는 데 유용합니다.
    예를 들어 '2024년 6월 10일의 5번 토픽에 대한 키워드 분석'과 같은 질문에 사용합니다.
    
    Args:
        analysis_date (str): 분석 날짜 (YYYY-MM-DD 형식, 예: 2024-06-10). 필수 항목입니다.
        topic_id (int): 분석할 토픽 ID. 필수 항목입니다.
        
    Returns:
        str: JSON 형식의 키워드 빈도 분석 결과
    """
    logger.info(f"get_topic_keyword_frequency 도구 호출: {analysis_date}, 토픽 ID: {topic_id}")
    conn = None
    try:
        conn = db_manager.get_db_connection()
        cursor = conn.cursor()
        
        # 토픽 정보 가져오기
        topic_query = """
        SELECT topic_name, representation, topic_count
        FROM topic_info 
        WHERE DATE(analysis_date) = %s AND topic_id = %s
        """
        cursor.execute(topic_query, (analysis_date, topic_id))
        topic_info = cursor.fetchone()
        
        if not topic_info:
            return json.dumps({"error": f"해당 날짜({analysis_date})와 토픽 ID({topic_id})에 대한 정보를 찾을 수 없습니다."}, ensure_ascii=False, indent=2)
        
        # 해당 토픽에 속한 기사들의 키워드 분석
        articles_query = """
        SELECT na.processed_text, tr.probability
        FROM news_articles na
        JOIN topic_results tr ON na.id = tr.article_id
        WHERE DATE(tr.analysis_date) = %s AND tr.topic_id = %s
        ORDER BY tr.probability DESC
        """
        cursor.execute(articles_query, (analysis_date, topic_id))
        articles = cursor.fetchall()
        
        # 키워드 빈도 계산
        keyword_freq = {}
        total_articles = len(articles)
        
        for article in articles:
            if article['processed_text']:
                words = article['processed_text'].split()
                for word in words:
                    if len(word) > 1:  # 한 글자 단어 제외
                        keyword_freq[word] = keyword_freq.get(word, 0) + 1
        
        # 상위 20개 키워드만 반환
        top_keywords = sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)[:20]
        
        result = {
            "topic_id": topic_id,
            "analysis_date": analysis_date,
            "topic_name": topic_info['topic_name'],
            "topic_count": topic_info['topic_count'],
            "representation": json.loads(topic_info['representation']) if topic_info['representation'] else [],
            "total_articles": total_articles,
            "top_keywords": [{"keyword": word, "frequency": freq} for word, freq in top_keywords]
        }
        
        logger.info(f"키워드 빈도 분석 완료: {total_articles}건 기사 분석")
        return json.dumps(result, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.error(f"get_topic_keyword_frequency 도구 실행 중 오류: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)
    finally:
        if conn:
            conn.close()

@mcp_server.tool()
async def get_topic_trends(
    days: int = 7, 
    topic_id: Optional[int] = None
) -> str:
    """
    최근 N일간의 뉴스 토픽 트렌드를 분석합니다.
    특정 토픽 ID의 추이를 확인하거나, 최근 주요 토픽들의 변화를 파악할 수 있습니다.
    예를 들어 '지난 7일간의 주요 뉴스 토픽 트렌드', '최근 한 달간의 10번 토픽 트렌드'와 같은 질문에 사용합니다.
    
    Args:
        days (int, optional): 분석할 기간 (일 단위, 기본값: 7일).
        topic_id (int, optional): 특정 토픽 ID로 필터링 (선택 사항). 이 값이 없으면 모든 주요 토픽의 트렌드를 반환합니다.
        
    Returns:
        str: JSON 형식의 토픽 트렌드 데이터 목록
    """
    logger.info(f"get_topic_trends 도구 호출: 최근 {days}일, 토픽 ID: {topic_id}")
    conn = None
    try:
        conn = db_manager.get_db_connection()
        cursor = conn.cursor()
        
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days-1)
        
        if topic_id:
            query = """
            SELECT 
                DATE(ti.analysis_date) as date,
                ti.topic_id,
                ti.topic_name,
                ti.topic_count,
                ti.representation
            FROM topic_info ti
            WHERE DATE(ti.analysis_date) BETWEEN %s AND %s
                AND ti.topic_id = %s
            ORDER BY ti.analysis_date DESC
            """
            cursor.execute(query, (start_date, end_date, topic_id))
        else:
            query = """
            SELECT 
                DATE(ti.analysis_date) as date,
                ti.topic_id,
                ti.topic_name,
                ti.topic_count,
                ti.representation
            FROM topic_info ti
            WHERE DATE(ti.analysis_date) BETWEEN %s AND %s
                AND ti.topic_count >= 10
            ORDER BY ti.analysis_date DESC, ti.topic_count DESC
            """
            cursor.execute(query, (start_date, end_date))
        
        results = cursor.fetchall()
        
        processed_results = []
        for row in results:
            processed_row = {
                "date": str(row['date']),
                "topic_id": row['topic_id'],
                "topic_name": row['topic_name'],
                "topic_count": row['topic_count'],
                "representation": json.loads(row['representation']) if row['representation'] else []
            }
            processed_results.append(processed_row)
        
        logger.info(f"토픽 트렌드 분석 완료: {len(processed_results)}건")
        return json.dumps({
            "period_days": days,
            "topic_id_filter": topic_id,
            "trends": processed_results
        }, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.error(f"get_topic_trends 도구 실행 중 오류: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)
    finally:
        if conn:
            conn.close()


# main 함수를 weather.py와 동일하게 수정합니다.
if __name__ == "__main__":
    logger.info("뉴스 토픽 분석 MCP 서버 시작")
    try:
        # 데이터베이스 연결 테스트
        if not asyncio.run(db_manager.test_db_connection()): # asyncio.run으로 비동기 함수 호출
            logger.error("데이터베이스 연결 실패로 서버를 시작할 수 없습니다.")
            sys.exit(1)
            
        logger.info("FastMCP 서버 초기화 완료, 클라이언트 연결 대기 중...")
        mcp_server.run() # <--- weather.py와 동일한 실행 방식
            
    except Exception as e:
        logger.error(f"서버 시작 중 오류 발생: {e}")
        sys.exit(1)