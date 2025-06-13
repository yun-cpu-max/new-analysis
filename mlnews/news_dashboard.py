import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pymysql
import json
import pytz
import warnings

# 경고 메시지 무시
warnings.filterwarnings('ignore')

# --- 설정 ---
# MySQL 데이터베이스 설정 (본인의 MySQL 정보로 변경하세요!)
MYSQL_HOST = "localhost"
MYSQL_USER = "root"
MYSQL_PASSWORD = "mysql@24!"
MYSQL_DB = "news_analysis_db"

# --- 데이터베이스 유틸리티 함수 ---
@st.cache_resource
def get_mysql_connection():
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
    except pymysql.Error as e:
        st.error(f"데이터베이스 연결 오류: {e}")
        return None

def fetch_analysis_dates(conn):
    """데이터베이스에 저장된 모든 고유 분석 날짜를 가져옵니다."""
    if not conn:
        return []
    try:
        with conn.cursor() as cursor:
            # 실제 기사가 존재하는 날짜만 고려합니다.
            cursor.execute("SELECT DISTINCT DATE(analysis_date) AS analysis_date FROM news_articles ORDER BY analysis_date DESC;")
            results = cursor.fetchall()
            return [row['analysis_date'] for row in results]
    except pymysql.Error as e:
        st.error(f"분석 날짜 조회 오류: {e}")
        return []

def fetch_articles_and_topics_by_date_range(conn, start_date, end_date):
    """
    지정된 날짜 범위 내의 뉴스 기사와 할당된 토픽을 가져옵니다.
    기사 데이터와 토픽 결과 및 토픽 정보가 조인된 형태로 반환합니다.
    """
    if not conn:
        return pd.DataFrame()
    try:
        with conn.cursor() as cursor:
            sql = """
            SELECT
                DATE(na.analysis_date) AS analysis_day,
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
            ORDER BY
                na.analysis_date DESC, tr.probability DESC;
            """
            cursor.execute(sql, (start_date, end_date))
            data = cursor.fetchall()
            df = pd.DataFrame(data)

            # representation 문자열을 리스트로 다시 변환
            if 'representation' in df.columns:
                df['representation'] = df['representation'].apply(lambda x: json.loads(x) if x else [])

            return df
    except pymysql.Error as e:
        st.error(f"기간별 기사 데이터 조회 오류: {e}")
        return pd.DataFrame()

# --- Streamlit 애플리케이션 함수 ---

def display_topic_analysis_results(df, selected_date_for_display):
    """선택된 날짜의 토픽 분석 결과를 표시합니다 (막대 그래프, 키워드, 기사 목록)."""
    
    if df.empty:
        st.warning(f"선택된 날짜 ({selected_date_for_display.strftime('%Y-%m-%d')})에 대한 분석 데이터가 없습니다.")
        return

    # 노이즈 토픽(-1) 필터링
    df_filtered = df[df['topic_id'] != -1].copy()
    
    if df_filtered.empty:
        st.info("노이즈 토픽을 제외한 유효한 토픽이 없습니다.")
        return

    # 토픽별 기사 수 집계 및 토픽 정보 병합
    topic_counts_for_day = df_filtered.groupby('topic_name').size().reset_index(name='count')
    # Merge with topic info to get representation. Ensure unique representation per topic_name.
    # We need to get topic_id and representation for the selected date from the original single_day_df_filtered.
    topic_info_for_day = df_filtered[['topic_id', 'topic_name', 'representation']].drop_duplicates(subset=['topic_id', 'topic_name'])
    topic_info_for_day = topic_info_for_day[topic_info_for_day['topic_id'] != -1] # Exclude noise topic

    topic_overview_df = pd.merge(topic_counts_for_day, topic_info_for_day, on='topic_name', how='left')
    topic_overview_df = topic_overview_df.rename(columns={'count': 'topic_count'})
    topic_overview_df = topic_overview_df.sort_values(by='topic_count', ascending=False)

    # --- 상위 10개 토픽만 선택 ---
    top_10_topics_df = topic_overview_df.head(10)


    col1, col2 = st.columns([0.7, 0.3])

    with col1:
        # 상위 10개 토픽으로 막대 그래프 그리기
        fig = px.bar(
            top_10_topics_df,
            x='topic_name',
            y='topic_count',
            title='상위 10개 토픽별 기사 수', # 제목 변경
            labels={'topic_name': '토픽', 'topic_count': '기사 수'},
            hover_data={'representation': True},
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig.update_layout(xaxis={'categoryorder':'total descending'}, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("### 주요 토픽 정보")
        # 상위 5개 토픽 정보 표시 (기존과 동일)
        for index, row in topic_overview_df.head(5).iterrows():
            st.markdown(f"**토픽 {row['topic_id']}**: {row['topic_name']}")
            st.markdown(f"**기사 수**: {row['topic_count']}")
            st.markdown(f"**핵심 키워드**: {', '.join(row['representation'])}")
            st.markdown("---")

    st.subheader("📰 토픽별 기사 목록")

    # 토픽 선택 박스는 여전히 모든 토픽을 포함합니다. (특정 토픽의 기사 목록 확인 목적)
    selected_topic_name_for_articles = st.selectbox(
        "자세히 볼 토픽 선택",
        options=['전체 기사'] + topic_overview_df['topic_name'].tolist(),
        key=f"articles_select_{selected_date_for_display.strftime('%Y%m%d')}"
    )

    display_articles_df = df_filtered.copy()
    if selected_topic_name_for_articles != '전체 기사':
        display_articles_df = display_articles_df[display_articles_df['topic_name'] == selected_topic_name_for_articles]
    
    display_articles_df['pub_date_dt'] = pd.to_datetime(display_articles_df['pub_date'])
    display_articles_df = display_articles_df.sort_values(by=['probability', 'pub_date_dt'], ascending=[False, False])

    if not display_articles_df.empty:
        for index, row in display_articles_df.iterrows():
            with st.expander(f"**[{row['title']}]** (토픽: {row['topic_name']}, 확률: {row['probability']:.2f}) - {pd.to_datetime(row['pub_date']).strftime('%Y-%m-%d %H:%M:%S')}"):
                st.markdown(f"**원본 링크**: [{row['link']}]({row['link']})")
                st.markdown(f"**기사 요약**: {row['description']}")
            st.markdown("---")
    else:
        st.info("선택된 토픽에 해당하는 기사가 없습니다.")


def page_todays_topics(conn):
    """오늘의 토픽을 보여주는 페이지."""
    st.header("✨ 오늘의 토픽")
    st.markdown("가장 최근 분석된 날짜의 주요 뉴스 토픽을 확인하세요.")

    analysis_dates = fetch_analysis_dates(conn)
    if not analysis_dates:
        st.warning("데이터베이스에서 분석된 날짜를 찾을 수 없습니다. 뉴스 분석 스크립트를 먼저 실행해주세요.")
        return

    most_recent_date = analysis_dates[0] # 가장 최신 날짜
    st.info(f"분석 날짜: **{most_recent_date.strftime('%Y년 %m월 %d일')}**")

    recent_day_df = fetch_articles_and_topics_by_date_range(conn, most_recent_date, most_recent_date)
    display_topic_analysis_results(recent_day_df, most_recent_date)


def page_topic_trend_over_time(conn):
    """기간별 토픽 트렌드를 보여주는 페이지."""
    st.header("📈 기간별 토픽 트렌드 분석")
    st.markdown("선택한 기간 동안 뉴스 토픽의 변화를 그래프로 확인하세요.")

    analysis_dates = fetch_analysis_dates(conn)
    if not analysis_dates:
        st.warning("데이터베이스에서 분석된 날짜를 찾을 수 없습니다. 뉴스 분석 스크립트를 먼저 실행해주세요.")
        return

    min_date_available = min(analysis_dates)
    max_date_available = max(analysis_dates)

    col_start, col_end = st.columns(2)
    with col_start:
        start_date = st.date_input(
            "시작 날짜",
            value=max_date_available - timedelta(days=6), # 기본값: 최근 7일
            min_value=min_date_available,
            max_value=max_date_available
        )
    with col_end:
        end_date = st.date_input(
            "종료 날짜",
            value=max_date_available,
            min_value=min_date_available,
            max_value=max_date_available
        )

    if start_date > end_date:
        st.error("시작 날짜는 종료 날짜보다 빠르거나 같아야 합니다.")
        return

    st.info(f"분석 기간: **{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}**")
    
    trend_df = fetch_articles_and_topics_by_date_range(conn, start_date, end_date)

    if trend_df.empty:
        st.warning("선택된 기간에 대한 뉴스 데이터가 없습니다.")
        return

    # 노이즈 토픽(-1) 필터링
    trend_df_filtered = trend_df[trend_df['topic_id'] != -1].copy()

    if not trend_df_filtered.empty:
        # 날짜별, 토픽별 기사 수 집계
        topic_daily_counts = trend_df_filtered.groupby(['analysis_day', 'topic_name']).size().reset_index(name='article_count')
        
        # 기간 내 전체 기사 수 기준으로 상위 10개 토픽 선정
        top_topics_in_period = topic_daily_counts.groupby('topic_name')['article_count'].sum().nlargest(10).index.tolist()
        
        # 상위 토픽만 필터링
        topic_daily_counts_top = topic_daily_counts[topic_daily_counts['topic_name'].isin(top_topics_in_period)]

        if not topic_daily_counts_top.empty:
            fig_trend = px.line(
                topic_daily_counts_top,
                x='analysis_day',
                y='article_count',
                color='topic_name',
                title='기간별 주요 토픽 기사 수 추이 (상위 10개 토픽)', # 제목 유지 (이미 상위 10개만 필터링)
                labels={'analysis_day': '날짜', 'article_count': '기사 수', 'topic_name': '토픽 이름'},
                hover_data={'topic_name': True, 'article_count': True}
            )
            fig_trend.update_layout(hovermode="x unified")
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("선택된 기간 내에서 유효한 토픽이 없습니다.")
    else:
        st.info("선택된 기간에 노이즈 토픽을 제외한 유효한 토픽이 없습니다.")


def page_past_topics_from_db(conn):
    """DB에 저장된 과거 토픽을 보여주는 페이지."""
    st.header("🗓️ 과거 토픽 보기")
    st.markdown("데이터베이스에 저장된 특정 날짜의 토픽 분석 결과를 조회하세요.")

    analysis_dates = fetch_analysis_dates(conn)
    if not analysis_dates:
        st.warning("데이터베이스에서 분석된 날짜를 찾을 수 없습니다. 뉴스 분석 스크립트를 먼저 실행해주세요.")
        return

    selected_past_date = st.selectbox(
        "과거 분석 날짜 선택",
        options=analysis_dates,
        index=0, # 기본값으로 가장 최근 날짜
        format_func=lambda x: x.strftime('%Y년 %m월 %d일')
    )
    st.info(f"선택된 과거 분석 날짜: **{selected_past_date.strftime('%Y년 %m월 %d일')}**")

    past_day_df = fetch_articles_and_topics_by_date_range(conn, selected_past_date, selected_past_date)
    display_topic_analysis_results(past_day_df, selected_past_date)


# --- 메인 애플리케이션 실행 ---
if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="뉴스 토픽 분석 대시보드")

    st.sidebar.title("메뉴")
    
    # 사이드바에서 기능 선택
    page_selection = st.sidebar.radio(
        "기능을 선택하세요:",
        ("오늘의 토픽", "기간별 토픽 트렌드", "과거 토픽 보기")
    )

    conn = get_mysql_connection()
    if not conn:
        st.stop() # DB 연결 실패 시 앱 중단

    if page_selection == "오늘의 토픽":
        page_todays_topics(conn)
    elif page_selection == "기간별 토픽 트렌드":
        page_topic_trend_over_time(conn)
    elif page_selection == "과거 토픽 보기":
        page_past_topics_from_db(conn)

    st.markdown("---")
    st.markdown("앱에 대한 피드백이나 개선 사항이 있으시면 알려주세요!")