import os
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
from konlpy.tag import Okt
import re
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
import warnings
import pymysql # MySQL 연동
import pytz # 시간대 처리
import time # API 요청 지연을 위해


# 경고 메시지 무시 (예: 라이브러리의 UserWarning)
warnings.filterwarnings('ignore')

# --- 설정 ---
# 네이버 API 키 (본인의 CLIENT ID와 SECRET으로 변경하세요!)
NAVER_CLIENT_ID = "E0834SZ85ZrCc8PAqJUh"
NAVER_CLIENT_SECRET = "WHBeXZCjVh"
NAVER_NEWS_API_URL = "https://openapi.naver.com/v1/search/news.json"

# MySQL 데이터베이스 설정 (본인의 MySQL 정보로 변경하세요!)
MYSQL_HOST = "localhost"
MYSQL_USER = "root"
MYSQL_PASSWORD = "mysql@24!"
MYSQL_DB = "news_analysis_db" # 생성한 데이터베이스 이름과 일치하는지 확인

# --- Okt 초기화 ---
try:
    okt = Okt()
except Exception as e:
    print(f"Okt 초기화 오류: {e}. 'pip install konlpy' 및 Java 설치를 확인해주세요.")
    exit()  # Okt 없이는 진행 불가

# --- 전처리 함수 ---
def preprocess_korean_text(text):
    if not okt:
        return ""
    # HTML 태그, 특수 문자 및 추가 공백 제거
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[^가-힣a-zA-Z\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()

    stopwords = ['은', '는', '이', '가', '을', '를', '에', '에서', '와', '과', '하다', '이다', '되다', '되', '것', '수', '고', '다', '습니다', '등', '있다', '있', '으로', '에게', '하여', '이번', '지난', '말', '기자', '사진', '씨', '명', '년', '월', '일', '오전', '오후', '시', '분', '초', '지난달', '이번달', '새로운', '각각', '오직', '특히', '점', '또한', '통해', '이번', '그간', '따라', '대한', '관련', '때문', '로부터', '까지', '바로', '또한', '물론', '대비', '위해', '으로']

    processed_tokens = []
    for word, pos in okt.pos(text, norm=True, stem=True):
        if pos in ['Noun', 'Verb', 'Adjective', 'Exclamation', 'Josa']:
            if word not in stopwords and len(word) > 1:
                processed_tokens.append(word)
    return ' '.join(processed_tokens)

# --- 네이버 뉴스 API 호출 함수 ---
def get_naver_news_articles(query, display=100, start=1, sort='date'):
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    params = {
        "query": query,
        "display": display,
        "start": start,
        "sort": sort # 'date' (최신순) 또는 'sim' (유사도순)
    }
    try:
        response = requests.get(NAVER_NEWS_API_URL, headers=headers, params=params)
        response.raise_for_status() # HTTP 오류 (4xx 또는 5xx) 발생 시 예외 발생
        return response.json()['items']
    except requests.exceptions.RequestException as e:
        print(f"쿼리 '{query}'에 대한 네이버 뉴스 API 호출 오류: {e}")
        return []

# --- MySQL 연결 및 데이터 저장 함수 ---
def save_results_to_mysql(conn, doc_topic_df, topic_info_df, current_analysis_date):
    cursor = conn.cursor()

    # 1. news_articles 테이블에 기사 저장 (또는 링크가 존재하는 경우 업데이트)
    print("뉴스 기사 정보를 DB에 저장 중...")
    article_id_map = {} # link -> article_id 매핑
    
    # 중복 삽입 방지를 위해 ON DUPLICATE KEY UPDATE 사용
    insert_article_sql = """
    INSERT INTO news_articles (title, link, description, pub_date, original_text, processed_text, analysis_date)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        title=VALUES(title),
        description=VALUES(description),
        pub_date=VALUES(pub_date),
        original_text=VALUES(original_text),
        processed_text=VALUES(processed_text);
    """
    
    # 기존 기사 ID를 가져오거나 새로 삽입된 ID를 얻기 위해
    select_article_id_sql = "SELECT id FROM news_articles WHERE link = %s;"
    
    articles_to_insert = []
    for _, row in doc_topic_df.iterrows():
        # 네이버 API pubDate 포맷: 'Sat, 01 Jun 2024 23:30:00 +0900'
        # MySQL DATETIME 포맷으로 변환
        try:
            # pubDate_dt는 ISO 포맷으로 저장된 문자열이므로, 다시 파싱
            pub_date_dt = datetime.fromisoformat(row['pubDate']).replace(tzinfo=None) 
        except ValueError:
            pub_date_dt = datetime.now() # 파싱 실패 시 현재 시간 사용 또는 오류 처리
            print(f"Warning: Failed to parse pubDate '{row['pubDate']}'. Using current time.")

        articles_to_insert.append((
            row['title'], row['link'], row['original_text'], # description과 original_text를 동일하게 사용
            pub_date_dt,
            row['original_text'], row['processed_text'], current_analysis_date
        ))
        
    # executemany로 한 번에 여러 행 삽입 (효율성)
    # 하지만 ON DUPLICATE KEY UPDATE를 사용하면서 lastrowid를 개별적으로 얻기 어렵습니다.
    # 따라서, 각 행을 개별적으로 삽입하고 ID를 가져오는 방식으로 변경합니다.
    for article_data in articles_to_insert:
        link = article_data[1] # link 값은 튜플의 두 번째 요소
        cursor.execute(insert_article_sql, article_data)
        # MySQL에 ON DUPLICATE KEY UPDATE가 발생했을 때 lastrowid는 0을 반환합니다.
        # 따라서, 기존 ID를 가져오기 위한 추가 쿼리가 필요합니다.
        if cursor.rowcount == 0: # rowcount가 0이면 업데이트가 발생한 것 (이미 존재하는 링크)
            cursor.execute(select_article_id_sql, (link,))
            article_id = cursor.fetchone()['id']
        else: # rowcount가 1이면 새로운 삽입 발생
            article_id = cursor.lastrowid
        article_id_map[link] = article_id
    
    conn.commit()
    print(f"{len(article_id_map)}개의 기사 정보 저장 또는 업데이트 완료.")

    # 2. topic_results 테이블에 토픽 할당 결과 저장
    print("토픽 할당 결과를 DB에 저장 중...")
    insert_topic_result_sql = """
    INSERT INTO topic_results (article_id, topic_id, probability, analysis_date)
    VALUES (%s, %s, %s, %s);
    """
    results_to_insert = []
    for _, row in doc_topic_df.iterrows():
        article_id = article_id_map.get(row['link'])
        if article_id:
            results_to_insert.append((article_id, int(row['topic']), float(row['probability']), current_analysis_date))
    
    if results_to_insert:
        # executemany는 여러 행을 효율적으로 삽입
        cursor.executemany(insert_topic_result_sql, results_to_insert)
    conn.commit()
    print(f"{len(results_to_insert)}개의 토픽 할당 결과 저장 완료.")

    # 3. topic_info 테이블에 토픽 정보 저장
    print("토픽 정보를 DB에 저장 중...")
    insert_topic_info_sql = """
    INSERT INTO topic_info (topic_id, topic_count, topic_name, representation, analysis_date)
    VALUES (%s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        topic_count=VALUES(topic_count),
        topic_name=VALUES(topic_name),
        representation=VALUES(representation);
    """
    info_to_insert = []
    for _, row in topic_info_df.iterrows():
        # Representation 리스트를 JSON 문자열로 변환하여 저장
        # 비어있으면 '[]'로 저장
        representation = row['Representation']
        if not representation or (isinstance(representation, float) and pd.isna(representation)):
            representation_str = "[]"
        else:
            representation_str = json.dumps(representation, ensure_ascii=False)
        info_to_insert.append((
            int(row['Topic']), int(row['Count']), row['Name'], representation_str, current_analysis_date
        ))
    
    if info_to_insert:
        cursor.executemany(insert_topic_info_sql, info_to_insert)
    conn.commit()
    print(f"{len(info_to_insert)}개의 토픽 정보 저장 완료.")
    
    cursor.close()

# --- 메인 분석 함수 ---
def run_daily_analysis():
    current_analysis_date = datetime.now() # 분석이 수행된 날짜 및 시간 기록
    print(f"[{current_analysis_date.strftime('%Y-%m-%d %H:%M:%S')}] 일일 뉴스 분석 시작...")

    conn = None
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            db=MYSQL_DB,
            charset='utf8mb4', # 이모지 등 지원을 위해 utf8mb4 사용
            cursorclass=pymysql.cursors.DictCursor # 딕셔너리 형태로 결과 반환
        )
        print("MySQL 데이터베이스 연결 성공!")

        # 주요 뉴스 키워드
        queries = ['경제', '사회', '정치', '국제', '문화', 'IT', '과학', '부동산', '증시', '인공지능', '환경', '교육', '건강']
        all_articles = []
        
        kst_timezone = pytz.timezone('Asia/Seoul')
        
        # 지난 24시간 이내 기사만 필터링 (Naver API의 pubDate는 RFC 2822 포맷, KST 기준)
        filter_start_time = datetime.now(kst_timezone) - timedelta(hours=24)

        for q in queries:
            current_start = 1
            # 각 쿼리당 최대 1000개 기사 (네이버 API 제한)를 가져오면서 24시간 필터링
            while current_start <= 1000:
                items = get_naver_news_articles(q, display=100, start=current_start, sort='date')
                if not items:
                    break # 더 이상 기사가 없으면 중단
                
                new_articles_in_window = 0
                for item in items:
                    pub_date_str = item.get('pubDate')
                    if pub_date_str:
                        try:
                            # 날짜 파싱 (RFC 2822 포맷)
                            pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %z')
                            # 한국 시간대 +0900으로 변환 (네이버 기본)
                            pub_date_kst = pub_date.astimezone(kst_timezone)
                            
                            # 24시간 이내 기사만 필터링
                            if pub_date_kst >= filter_start_time:
                                # HTML 엔티티를 일반 문자로 디코딩
                                decoded_title = item.get('title', '').replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                                decoded_description = item.get('description', '').replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                                
                                all_articles.append({
                                    'title': decoded_title,
                                    'link': item.get('link', ''),
                                    'description': decoded_description, # description을 원문으로 사용
                                    'pubDate': pub_date_kst.isoformat(), # ISO 포맷으로 저장
                                    'original_text': decoded_description
                                })
                                new_articles_in_window += 1
                            else:
                                # 날짜순 정렬이므로, 24시간 범위를 벗어나면 이 쿼리에선 더 이상 최신 기사가 없음
                                # 다음 쿼리로 넘어가거나, 굳이 더 이상 검색할 필요 없음 (효율성)
                                pass 
                        except ValueError as ve:
                            print(f"날짜 파싱 오류: {pub_date_str} - {ve}")
                        except Exception as ex:
                            print(f"기사 처리 중 알 수 없는 오류: {ex}")
                
                # 현재 페이지에서 24시간 이내 기사가 없으면 다음 쿼리로 이동
                if new_articles_in_window == 0:
                    break
                    
                current_start += 100
                time.sleep(0.1) # API 요청 간 지연

        # 중복 기사 제거 (링크 기준으로)
        articles_df = pd.DataFrame(all_articles).drop_duplicates(subset=['link'])
        
        # pubDate를 datetime 객체로 변환하여 정확한 시간 필터링
        articles_df['pubDate_dt'] = pd.to_datetime(articles_df['pubDate'])
        articles_df_filtered_24h = articles_df[articles_df['pubDate_dt'] >= filter_start_time].copy() # .copy() 경고 방지

        original_documents_final = articles_df_filtered_24h['original_text'].tolist()
        article_titles_final = articles_df_filtered_24h['title'].tolist()
        article_links_final = articles_df_filtered_24h['link'].tolist()
        article_pubdates_final = articles_df_filtered_24h['pubDate'].tolist() # ISO 포맷 문자열 그대로 전달

        if not original_documents_final:
            print("수집된 뉴스 기사가 없습니다. 분석을 건너뜜.")
            return

        print(f"총 {len(original_documents_final)}개의 24시간 이내 기사 수집 완료. 전처리 시작...")

        processed_documents = [preprocess_korean_text(doc) for doc in original_documents_final]

        # 전처리 후 빈 문서 제거
        valid_original_docs = []
        valid_processed_docs = []
        valid_titles = []
        valid_links = []
        valid_pubdates = []
        
        for i, doc in enumerate(processed_documents):
            if doc.strip(): # 빈 문자열이 아닌 경우에만 포함
                valid_processed_docs.append(doc)
                valid_original_docs.append(original_documents_final[i])
                valid_titles.append(article_titles_final[i])
                valid_links.append(article_links_final[i])
                valid_pubdates.append(article_pubdates_final[i])
        
        if not valid_processed_docs:
            print("전처리 후 유효한 문서가 없습니다. 분석을 건너뜜.")
            return

        print(f"유효한 문서 {len(valid_processed_docs)}개로 토픽 모델링 시작...")

        embedding_model = SentenceTransformer('jhgan/ko-sbert-nli')
        # show_progress_bar는 터미널 실행 시 True로 두면 진행 상황을 볼 수 있음
        embeddings = embedding_model.encode(valid_processed_docs, show_progress_bar=True)

        topic_model = BERTopic(
            language="korean",
            embedding_model=embedding_model,
            nr_topics='auto', # 자동으로 토픽 개수 결정
            top_n_words=10, # 각 토픽당 상위 10개 키워드
            min_topic_size=10, # 최소 토픽 크기
            calculate_probabilities=True # 각 문서가 토픽에 속할 확률 계산
        )
        topics, probs = topic_model.fit_transform(valid_processed_docs, embeddings)

        try:
            # -1 토픽 (노이즈) 제거 및 문서 재할당 시도
            # reduce_outliers는 topics를 업데이트합니다.
            new_topics = topic_model.reduce_outliers(valid_processed_docs, topics, strategy="embeddings")
            topics = new_topics # 업데이트된 topics 사용

            # get_document_info를 사용하여 할당된 토픽과 해당 확률을 가져옵니다.
            # 이 방식이 가장 정확하며, 오류를 방지할 수 있습니다.
            doc_info = topic_model.get_document_info(valid_processed_docs)
            # doc_info['Probability']는 각 문서가 할당된 토픽의 확률입니다.
            assigned_probabilities = doc_info['Probability'].tolist()
            
        except Exception as e:
            print(f"토픽 노이즈 제거 또는 확률 계산 중 오류 발생: {e}. 이 단계를 건너뛰고 초기 값으로 진행합니다.")
            # 오류 발생 시, topics와 probs를 초기 값으로 유지하고,
            # probs가 2D 배열인 경우 0으로 초기화된 확률 리스트를 사용합니다.
            # 이 경우, DB에 저장되는 확률 값은 의미가 없거나 잘못될 수 있습니다.
            # 따라서 예외 처리보다는 정확한 데이터 흐름을 목표로 해야 합니다.
            # 만약 `get_document_info`가 작동하지 않는 극단적인 상황이라면,
            # 아래와 같이 0으로 채워진 리스트를 사용하는 것이 오류 방지를 위한 임시 방편이 될 수 있습니다.
            assigned_probabilities = [0.0] * len(topics)


        freq = topic_model.get_topic_info()

        doc_topic_df_for_db = pd.DataFrame({
            'title': valid_titles,
            'link': valid_links,
            'pubDate': valid_pubdates, # ISO 포맷 문자열
            'original_text': valid_original_docs,
            'processed_text': valid_processed_docs,
            'topic': topics, # reduce_outliers로 업데이트된 topics
            'probability': assigned_probabilities # 단일 확률 값 리스트
        })

        # DB에 결과 저장
        save_results_to_mysql(conn, doc_topic_df_for_db, freq, current_analysis_date)

    except pymysql.Error as e:
        print(f"MySQL DB 연결 또는 작업 중 오류 발생: {e}")
    except Exception as e:
        print(f"분석 또는 DB 저장 중 심각한 오류 발생: {e}")
    finally:
        if conn:
            conn.close()
            print("MySQL 데이터베이스 연결 종료.")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 일일 뉴스 분석 완료.")

if __name__ == "__main__":
    # 폰트 경로 확인용 (필요시 사용)
    # import os
    # print(os.path.exists('/System/Library/Fonts/AppleSDGothicNeo.ttc')) # macOS
    # print(os.path.exists('C:/Windows/Fonts/malgun.ttf')) # Windows

    run_daily_analysis()