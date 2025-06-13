import streamlit as st
import pandas as pd
import os
import matplotlib.pyplot as plt
from wordcloud import WordCloud
import plotly.express as px
import pymysql # MySQL 연동
import json # JSON 문자열 파싱을 위해
from datetime import datetime, timedelta

# 폰트 설정 (사용자 OS에 따라 변경 필요)
try:
    plt.rcParams['font.family'] = 'AppleGothic'
except:
    try:
        plt.rcParams['font.family'] = 'Malgun Gothic'
    except:
        st.warning("시스템 폰트 설정에 문제가 있어 한글이 깨질 수 있습니다. 'AppleGothic' 또는 'Malgun Gothic' 폰트가 설치되어 있는지 확인해주세요.")
plt.rcParams['axes.unicode_minus'] = False # 마이너스 기호 깨짐 방지

# MySQL 설정 (daily_news_analyzer.py와 동일해야 함)
MYSQL_HOST = "localhost"
MYSQL_USER = "root"
MYSQL_PASSWORD = "mysql@24!"
MYSQL_DB = "news_analysis_db" # 생성한 데이터베이스 이름과 일치하는지 확인

# --- MySQL에서 데이터 로드 함수 ---
@st.cache_data(ttl=300) # 5분마다 캐시 갱신 (새로운 분석 결과 반영)
def load_analysis_results_from_mysql(analysis_date_str):
    conn = None
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            db=MYSQL_DB,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        
        analysis_date = datetime.strptime(analysis_date_str, '%Y-%m-%d')
        
        # news_articles 및 topic_results 조인하여 가져오기
        # analysis_date를 기준으로 데이터를 가져옴
        select_articles_sql = """
        SELECT
            na.title,
            na.link,
            na.original_text,
            tr.topic_id AS topic,
            tr.probability,
            na.pub_date,
            na.analysis_date
        FROM news_articles na
        JOIN topic_results tr ON na.id = tr.article_id
        WHERE DATE(na.analysis_date) = %s;
        """
        # read_sql의 params는 튜플 형태로 전달해야 함
        doc_topic_df = pd.read_sql(select_articles_sql, conn, params=(analysis_date.strftime('%Y-%m-%d'),))
        
        # topic_info 테이블에서 토픽 정보 가져오기
        select_topic_info_sql = """
        SELECT
            topic_id AS Topic,
            topic_count AS `Count`,
            topic_name AS Name,
            representation AS Representation
        FROM topic_info
        WHERE DATE(analysis_date) = %s;
        """
        freq_df = pd.read_sql(select_topic_info_sql, conn, params=(analysis_date.strftime('%Y-%m-%d'),))
        
        # Representation 컬럼은 JSON 문자열로 저장되었으므로 다시 리스트로 변환
        if 'Representation' in freq_df.columns:
            # === 이 부분을 다음과 같이 수정합니다. ===
            freq_df['Representation'] = freq_df['Representation'].apply(
                lambda x: json.loads(x) if isinstance(x, str) and x.strip() else []
            )
            # ======================================

        return doc_topic_df, freq_df, analysis_date

    except pymysql.Error as e:
        st.error(f"MySQL 데이터 로드 중 오류 발생: {e}. MySQL 서버가 실행 중인지, 인증 정보가 올바른지 확인해주세요.")
        return None, None, None
    except json.JSONDecodeError as e: # JSON 파싱 오류 처리 추가
        # 이 메시지가 뜨면 DB에 유효하지 않은 JSON이 있다는 뜻이므로, DB를 확인해야 함
        st.error(f"데이터 처리 중 예상치 못한 오류 발생: Representation 컬럼 JSON 파싱 오류: {e}. DB의 해당 데이터가 유효한 JSON 형식인지 확인해주세요.")
        return None, None, None
    except Exception as e:
        st.error(f"데이터 처리 중 예상치 못한 오류 발생: {e}")
        return None, None, None
    finally:
        if conn:
            conn.close()

# --- MySQL에서 분석이 수행된 날짜 목록 가져오기 ---
@st.cache_data(ttl=3600) # 1시간마다 갱신 (새로운 분석 날짜가 추가될 수 있으므로)
def get_available_analysis_dates():
    conn = None
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            db=MYSQL_DB,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        cursor = conn.cursor()
        # analysis_date가 있는 모든 고유한 날짜를 최신순으로 가져옴
        cursor.execute("SELECT DISTINCT DATE(analysis_date) AS distinct_date FROM news_articles ORDER BY distinct_date DESC;")
        dates = [row['distinct_date'].strftime('%Y-%m-%d') for row in cursor.fetchall()]
        return dates
    except pymysql.Error as e:
        st.error(f"MySQL에서 분석 날짜 목록을 가져오는 중 오류 발생: {e}")
        return []
    finally:
        if conn:
            conn.close()

# --- 이슈 순위화 함수 ---
def rank_issues(topic_freq_df):
    ranked_df = topic_freq_df[topic_freq_df.Topic != -1].copy() # 노이즈 토픽(-1) 제외
    ranked_df = ranked_df.sort_values(by='Count', ascending=False) # 문서 수 기준으로 내림차순 정렬
    ranked_df = ranked_df[['Topic', 'Count', 'Name', 'Representation']]
    ranked_df.rename(columns={'Name': '대표 키워드 그룹', 'Representation': '핵심 키워드'}, inplace=True)
    return ranked_df

# --- 시각화 함수 ---
def plot_wordcloud(topic_id, words_scores):
    if topic_id == -1:
        st.warning("선택된 토픽은 노이즈 토픽(-1)입니다. 워드클라우드를 생성할 수 없습니다.")
        return
    
    if not words_scores:
        st.warning(f"토픽 {topic_id}에 대한 키워드가 없습니다.")
        return

    word_freq = {word: score for word, score in words_scores}
    
    font_path = None
    # macOS 폰트 경로 (예시)
    if 'AppleGothic' in plt.rcParams['font.family'] and os.path.exists('/System/Library/Fonts/AppleSDGothicNeo.ttc'):
        font_path = '/System/Library/Fonts/AppleSDGothicNeo.ttc'
    # Windows 폰트 경로 (예시)
    elif 'Malgun Gothic' in plt.rcParams['font.family'] and os.path.exists('C:/Windows/Fonts/malgun.ttf'):
        font_path = 'C:/Windows/Fonts/malgun.ttf'
    
    if font_path and os.path.exists(font_path):
        wc = WordCloud(font_path=font_path,
                       width=800, height=400, background_color='white',
                       max_words=50, collocations=False).generate_from_frequencies(word_freq)
    else:
        st.warning(f"워드클라우드 폰트 경로를 찾을 수 없습니다. (경로: {font_path}) 기본 폰트로 생성합니다.")
        wc = WordCloud(width=800, height=400, background_color='white',
                       max_words=50, collocations=False).generate_from_frequencies(word_freq)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(wc, interpolation='bilinear')
    ax.axis('off')
    st.pyplot(fig)

def plot_topic_distribution(freq_df):
    # 노이즈 토픽(-1)을 제외하고 상위 10개 토픽만 시각화
    filtered_freq_df = freq_df[freq_df.Topic != -1].head(10)
    if filtered_freq_df.empty:
        st.info("표시할 토픽 분포가 없습니다.")
        return
    
    fig = px.bar(filtered_freq_df, x='Topic', y='Count', 
                 title='상위 10개 토픽 문서 수 분포', 
                 hover_data=['Representation'], # 마우스 오버 시 핵심 키워드 표시
                 labels={'Topic': '토픽 ID', 'Count': '문서 수'},
                 color_discrete_sequence=px.colors.qualitative.Pastel) # 색상 팔레트
    fig.update_xaxes(type='category') # X축을 카테고리형으로 설정
    st.plotly_chart(fig, use_container_width=True) # 컨테이너 너비에 맞춤

# --- Streamlit 앱 메인 로직 ---
def main():
    st.set_page_config(layout="wide") # 넓은 레이아웃 사용
    st.title("☀️ 굿모닝, 오늘의 뉴스 이슈 대시보드")
    st.write("매일 아침 자동으로 분석된 최신 뉴스 이슈와 과거 데이터를 확인하세요.")
    
    st.sidebar.header("분석 날짜 선택")
    available_dates = get_available_analysis_dates() # MySQL에서 분석 날짜 목록 가져오기
    
    if not available_dates:
        st.error("MySQL 데이터베이스에서 분석된 날짜를 찾을 수 없습니다. 'daily_news_analyzer.py' 스크립트가 실행되었는지, 그리고 MySQL 설정이 올바른지 확인해주세요.")
        st.stop() # 더 이상 진행하지 않고 앱 종료

    # 가장 최신 날짜를 기본값으로 선택
    selected_date_str = st.sidebar.selectbox("분석 날짜 선택:", available_dates)

    doc_topic_df, freq_df, analysis_time = load_analysis_results_from_mysql(selected_date_str)

    # analysis_time이 None일 수 있으므로 명시적으로 체크
    if doc_topic_df is None or freq_df is None or analysis_time is None: 
        st.info("선택된 날짜의 분석 결과를 로드할 수 없습니다. 데이터가 MySQL에 있는지 확인해주세요.")
        st.stop()

    st.sidebar.info(f"선택된 분석 시각: **{analysis_time.strftime('%Y년 %m월 %d일')}**")
    st.sidebar.info(f"총 분석 기사 수: **{len(doc_topic_df)}개**")
    st.sidebar.info(f"총 발견 토픽 수: **{len(freq_df[freq_df.Topic != -1])}개**")

    st.markdown("---")
    st.header(f"📊 {analysis_time.strftime('%Y년 %m월 %d일')} 주요 이슈 분석 결과")

    # 탭 구성
    tab1, tab2 = st.tabs(["주요 이슈 요약", "토픽 상세 분석"])

    with tab1:
        st.subheader("💡 핵심 뉴스 이슈 (TOP 5)")
        ranked_issues_df = rank_issues(freq_df)
        if not ranked_issues_df.empty:
            st.dataframe(ranked_issues_df.head(5).style.set_properties(**{'font-size': '16px'}), use_container_width=True, hide_index=True)
        else:
            st.info("분석된 주요 이슈가 없습니다.")

        st.markdown("---")
        st.subheader("📈 토픽 문서 수 분포 (상위 10개)")
        plot_topic_distribution(freq_df)

    with tab2:
        st.subheader("🔍 특정 토픽 상세 분석")
        
        available_topics = sorted(freq_df[freq_df.Topic != -1]['Topic'].tolist())
        if not available_topics:
            st.info("분석된 토픽이 없습니다.")
            return

        # 토픽 ID 선택 드롭다운 (토픽 ID와 핵심 키워드를 함께 표시)
        selected_topic = st.selectbox(
            "분석할 토픽 ID를 선택하세요:", 
            options=available_topics,
            # freq.Topic 이 아니라 freq_df.Topic 입니다.
            format_func=lambda x: f"토픽 {x} ({', '.join(freq_df[freq_df.Topic == x]['Representation'].iloc[0])})" 
        )

        if selected_topic is not None:
            st.write(f"#### 선택된 토픽: **{selected_topic}**")
            topic_info = freq_df[freq_df.Topic == selected_topic]
            if not topic_info.empty:
                st.write(f"- **문서 수:** {topic_info['Count'].iloc[0]}개")
                st.write(f"- **대표 키워드 그룹:** {topic_info['Name'].iloc[0]}")
                st.write(f"- **핵심 키워드:** {', '.join(topic_info['Representation'].iloc[0])}")
                
            st.markdown("---")
            st.subheader(f"워드클라우드 (토픽 {selected_topic})")
            # BERTopic의 get_topic()처럼 토픽 키워드와 점수를 함께 제공하기 어렵기 때문에
            # Representation의 각 키워드에 임시로 1.0 점수를 부여하여 워드클라우드 생성
            # Representation이 비어있을 경우에 대한 처리 추가
            if not topic_info.empty and topic_info['Representation'].iloc[0]: # 비어있는 리스트 여부 확인 추가
                plot_wordcloud(selected_topic, [(word, 1.0) for word in topic_info['Representation'].iloc[0]])
            else:
                st.warning("이 토픽에 대한 워드클라우드를 생성할 키워드가 없습니다.")


            st.markdown("---")
            st.subheader(f"토픽 {selected_topic} 관련 뉴스 기사 예시")
            # 해당 토픽에 속하는 기사들을 확률 높은 순으로 정렬
            topic_articles_df = doc_topic_df[doc_topic_df.topic == selected_topic].sort_values(by='probability', ascending=False)
            
            if not topic_articles_df.empty:
                num_display_articles = st.slider("표시할 기사 수", 1, min(10, len(topic_articles_df)), 3)
                for i, row in topic_articles_df.head(num_display_articles).iterrows():
                    # st.expander를 사용하여 기사 내용을 숨기고 펼칠 수 있게 함
                    st.expander(f"**{row['title']}** (확률: {row['probability']:.2f})").markdown(f"*{row['link']}*\n\n{row['original_text']}")
            else:
                st.info(f"토픽 {selected_topic}에 해당하는 기사가 없습니다.")

if __name__ == "__main__":
    main()