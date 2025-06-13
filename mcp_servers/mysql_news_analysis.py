#!/usr/bin/env python3
import json
import pymysql
import sys
import os
from datetime import datetime, timedelta
import pandas as pd
import warnings
import asyncio
from typing import Any, Dict, List, Optional

warnings.filterwarnings('ignore')

# --- MySQL DB 설정 (본인의 정보로 변경) ---
MYSQL_HOST = "localhost" # 또는 "127.0.0.1"
MYSQL_USER = "root"
MYSQL_PASSWORD = "mysql@24!"
MYSQL_DB = "news_analysis_db"

def get_db_connection():
    """MySQL 데이터베이스 연결을 설정하고 반환합니다."""
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            db=MYSQL_DB,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except Exception as e:
        print(f"DB 연결 오류: {e}", file=sys.stderr)
        return None

def fetch_analysis_dates_from_db():
    """데이터베이스에 저장된 모든 고유 분석 날짜를 가져옵니다."""
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT DATE(analysis_date) AS analysis_date FROM news_articles ORDER BY analysis_date DESC;")
            results = cursor.fetchall()
            return [row['analysis_date'].strftime('%Y-%m-%d') for row in results]
    except Exception as e:
        print(f"분석 날짜 조회 오류: {e}", file=sys.stderr)
        return []
    finally:
        if conn:
            conn.close()

def convert_to_json_serializable(obj):
    """DataFrame의 값들을 JSON 직렬화 가능한 형태로 변환"""
    if pd.isna(obj):
        return None
    elif isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    elif isinstance(obj, pd.Series):
        return obj.to_dict()
    elif hasattr(obj, 'item'):  # numpy types
        return obj.item()
    else:
        return obj

def fetch_data_for_analysis(start_date_str: str, end_date_str: str, topic_id: int = None, keyword: str = None):
    """
    지정된 날짜 범위, 토픽 ID, 키워드에 따라 뉴스 기사, 토픽 결과, 토픽 정보를 가져옵니다.
    이 함수는 '오늘의 토픽', '기간별 트렌드', '과거 토픽', '특정 키워드/토픽 기사 목록'에 사용됩니다.
    """
    conn = get_db_connection()
    if not conn:
        return {"status": "error", "message": "DB 연결 실패."}

    try:
        with conn.cursor() as cursor:
            sql = """
            SELECT
                DATE(na.analysis_date) AS analysis_day,
                na.id AS article_id,
                na.title,
                na.link,
                na.description,
                na.pub_date,
                tr.topic_id,
                tr.probability,
                ti.topic_name,
                ti.representation
            FROM
                news_articles na
            JOIN
                topic_results tr ON na.id = tr.article_id
            LEFT JOIN
                topic_info ti ON tr.topic_id = ti.topic_id AND DATE(ti.analysis_date) = DATE(na.analysis_date)
            WHERE
                DATE(na.analysis_date) BETWEEN %s AND %s
            """
            params = [start_date_str, end_date_str]

            if topic_id is not None:
                sql += " AND tr.topic_id = %s"
                params.append(topic_id)
            
            if keyword:
                sql += " AND (na.title LIKE %s OR na.description LIKE %s)"
                params.append(f"%{keyword}%")
                params.append(f"%{keyword}%")

            sql += " ORDER BY na.analysis_date DESC, tr.probability DESC;"
            
            cursor.execute(sql, tuple(params))
            data = cursor.fetchall()

            if not data:
                msg = f"선택된 조건 ({start_date_str} ~ {end_date_str}"
                if topic_id is not None: msg += f", 토픽 ID: {topic_id}"
                if keyword: msg += f", 키워드: '{keyword}'"
                msg += ")에 대한 데이터가 없습니다."
                return {"status": "success", "message": msg}

            # 데이터 처리 - 노이즈 토픽(-1) 필터링
            filtered_data = []
            for row in data:
                if row['topic_id'] != -1:
                    # 날짜 객체를 문자열로 변환
                    if row['analysis_day']:
                        row['analysis_day'] = row['analysis_day'].strftime('%Y-%m-%d')
                    if row['pub_date']:
                        row['pub_date'] = row['pub_date'].strftime('%Y-%m-%d %H:%M:%S')
                    
                    # representation 문자열을 리스트로 변환
                    if row['representation']:
                        try:
                            if isinstance(row['representation'], str):
                                row['representation'] = json.loads(row['representation'])
                            elif not isinstance(row['representation'], list):
                                row['representation'] = []
                        except:
                            row['representation'] = []
                    else:
                        row['representation'] = []
                    
                    filtered_data.append(row)

            if not filtered_data:
                msg = f"선택된 조건 ({start_date_str} ~ {end_date_str}"
                if topic_id is not None: msg += f", 토픽 ID: {topic_id}"
                if keyword: msg += f", 키워드: '{keyword}'"
                msg += ")에 유효한 토픽(노이즈 제외) 데이터가 없습니다."
                return {"status": "success", "message": msg}

            return {"status": "success", "data": filtered_data}

    except Exception as e:
        print(f"데이터 조회 오류: {e}", file=sys.stderr)
        return {"status": "error", "message": str(e)}
    finally:
        if conn:
            conn.close()

def get_topic_keyword_frequency(analysis_date_str: str, topic_id: int):
    """
    특정 날짜의 특정 토픽에서 가장 자주 등장하는 키워드를 추출하여 빈도와 함께 보여줍니다.
    (DB의 representation 필드를 활용하여, 이미 추출된 키워드 목록을 사용)
    """
    conn = get_db_connection()
    if not conn:
        return {"status": "error", "message": "DB 연결 실패."}
    
    try:
        with conn.cursor() as cursor:
            # 해당 날짜, 해당 토픽의 representation (키워드 목록)을 가져옴
            sql = """
            SELECT representation
            FROM topic_info
            WHERE DATE(analysis_date) = %s AND topic_id = %s;
            """
            cursor.execute(sql, (analysis_date_str, topic_id))
            result = cursor.fetchone()

            if not result or not result['representation']:
                return {"status": "success", "message": f"날짜 {analysis_date_str}, 토픽 ID {topic_id}에 대한 키워드 정보가 없습니다."}

            keywords_str = result['representation']
            try:
                if isinstance(keywords_str, str):
                    keywords_list = json.loads(keywords_str) # JSON 문자열을 파이썬 리스트로 변환
                elif isinstance(keywords_str, list):
                    keywords_list = keywords_str
                else:
                    keywords_list = []
            except:
                keywords_list = []

            return {"status": "success", "topic_id": topic_id, "analysis_date": analysis_date_str, "keywords": keywords_list}

    except Exception as e:
        print(f"키워드 빈도 조회 오류: {e}", file=sys.stderr)
        return {"status": "error", "message": str(e)}
    finally:
        if conn:
            conn.close()

# MCP 서버 구현
class NewsAnalysisMCPServer:
    def __init__(self):
        self.tools = [
            {
                "name": "get_available_analysis_dates",
                "description": "MySQL 데이터베이스에서 뉴스 분석 데이터가 존재하는 모든 날짜 목록을 조회합니다.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "get_news_analysis_data",
                "description": "MySQL 데이터베이스에서 지정된 시작 날짜부터 종료 날짜까지의 뉴스 토픽 분석 데이터를 조회합니다.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "format": "date",
                            "description": "조회할 기간의 시작 날짜 (YYYY-MM-DD 형식)."
                        },
                        "end_date": {
                            "type": "string", 
                            "format": "date",
                            "description": "조회할 기간의 종료 날짜 (YYYY-MM-DD 형식)."
                        },
                        "topic_id": {
                            "type": "integer",
                            "description": "조회할 뉴스 토픽의 고유 ID입니다. (선택 사항)"
                        },
                        "keyword": {
                            "type": "string",
                            "description": "기사 제목 또는 내용에 포함된 검색할 키워드입니다. (선택 사항)"
                        }
                    },
                    "required": ["start_date", "end_date"]
                }
            },
            {
                "name": "get_topic_keyword_frequency",
                "description": "특정 날짜와 토픽 ID에 대한 핵심 키워드와 해당 키워드의 중요도를 조회합니다.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "analysis_date": {
                            "type": "string",
                            "format": "date", 
                            "description": "분석할 날짜 (YYYY-MM-DD 형식)."
                        },
                        "topic_id": {
                            "type": "integer",
                            "description": "분석할 뉴스 토픽의 고유 ID입니다."
                        }
                    },
                    "required": ["analysis_date", "topic_id"]
                }
            }
        ]

    def safe_json_dumps(self, obj):
        """안전한 JSON 직렬화"""
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            print(f"JSON 직렬화 오류: {e}", file=sys.stderr)
            return json.dumps({"error": "JSON 직렬화 실패"}, ensure_ascii=False)

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """MCP 요청을 처리합니다."""
        try:
            method = request.get("method")
            request_id = request.get("id")
            
            # ID 처리 개선
            if request_id is None:
                request_id = None
            elif isinstance(request_id, (str, int)):
                request_id = request_id
            else:
                request_id = str(request_id)
            
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "news-analysis-server",
                            "version": "1.0.0"
                        }
                    }
                }
                if request_id is not None:
                    response["id"] = request_id
                return response
            
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "result": {
                        "tools": self.tools
                    }
                }
                if request_id is not None:
                    response["id"] = request_id
                return response
            
            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                if tool_name == "get_available_analysis_dates":
                    result = {"available_dates": fetch_analysis_dates_from_db()}
                    
                elif tool_name == "get_news_analysis_data":
                    start_date = arguments.get("start_date")
                    end_date = arguments.get("end_date") 
                    topic_id = arguments.get("topic_id")
                    keyword = arguments.get("keyword")
                    
                    if not start_date or not end_date:
                        return {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {
                                "code": -32602,
                                "message": "시작 날짜와 종료 날짜가 필요합니다."
                            }
                        }
                    
                    result = fetch_data_for_analysis(start_date, end_date, topic_id, keyword)
                    
                elif tool_name == "get_topic_keyword_frequency":
                    analysis_date = arguments.get("analysis_date")
                    topic_id = arguments.get("topic_id")
                    
                    if not analysis_date or topic_id is None:
                        return {
                            "jsonrpc": "2.0", 
                            "id": request_id,
                            "error": {
                                "code": -32602,
                                "message": "analysis_date와 topic_id가 필요합니다."
                            }
                        }
                    
                    result = get_topic_keyword_frequency(analysis_date, topic_id)
                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32601,
                            "message": f"알 수 없는 도구: {tool_name}"
                        }
                    }
                
                response = {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": self.safe_json_dumps(result)
                            }
                        ]
                    }
                }
                if request_id is not None:
                    response["id"] = request_id
                return response
            
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"알 수 없는 메소드: {method}"
                    }
                }
        
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"내부 오류: {str(e)}"
                }
            }
            # id 처리
            if "id" in request:
                error_response["id"] = request["id"]
            return error_response

async def main():
    """메인 함수 - MCP 서버 실행"""
    server = NewsAnalysisMCPServer()
    
    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            
            try:
                request = json.loads(line.strip())
                response = await server.handle_request(request)
                print(json.dumps(response, ensure_ascii=False))
                sys.stdout.flush()
            except json.JSONDecodeError as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": f"JSON 파싱 오류: {str(e)}"
                    }
                }
                print(json.dumps(error_response, ensure_ascii=False))
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"서버 오류: {e}", file=sys.stderr)

if __name__ == "__main__":
    asyncio.run(main())