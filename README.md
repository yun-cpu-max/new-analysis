# 📰 뉴스 토픽 분석 시스템 (News Topic Analysis System)

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg?style=flat-square&logo=python)
![MySQL](https://img.shields.io/badge/MySQL-8.0+-blue.svg?style=flat-square&logo=mysql)
![BERTopic](https://img.shields.io/badge/BERTopic-v0.16.0-orange.svg?style=flat-square&logo=jupyter)
![FastMCP](https://img.io/badge/FastMCP-v0.1.0-green.svg?style=flat-square)
![Konlpy](https://img.shields.io/badge/Konlpy-v0.6.0-red.svg?style=flat-square)
![Naver API](https://img.shields.io/badge/Naver%20API-News-brightgreen.svg?style=flat-square)

## 🚀 프로젝트 개요

본 프로젝트는 방대한 온라인 뉴스 데이터 속에서 의미 있는 정보와 트렌드를 효율적으로 파악하기 위해 개발된 **뉴스 토픽 자동 분석 시스템**입니다. 네이버 뉴스 API를 통해 실시간 뉴스를 수집하고, 최신 토픽 모델링 기법인 BERTopic을 활용하여 뉴스 기사들의 주요 토픽을 자동으로 분류 및 분석합니다.

더 나아가, 시스템은 FastMCP 서버를 통해 LLM(Large Language Model)과 연동될 수 있도록 설계되었습니다. 이를 통해 사용자는 자연어 질의만으로도 뉴스 토픽 정보에 손쉽게 접근하고, 심층적인 분석 및 트렌드 파악을 요청할 수 있는 사용자 편의성을 극대화합니다.

### ❓ 왜 이 프로젝트를 만들었는가?

* **정보 과부하 해소**: 넘쳐나는 뉴스 속에서 핵심 내용을 파악하고 트렌드를 분석하는 데 드는 시간과 노력을 줄이고자 했습니다.
* **분석의 자동화 및 효율화**: 수동적인 뉴스 분류 및 키워드 기반 분석의 한계를 극복하고, 자동화된 토픽 모델링을 통해 보다 깊이 있는 인사이트를 제공하고자 했습니다.
* **LLM 연동 최적화**: LLM 사용 시 발생하는 긴 텍스트 응답으로 인한 토큰 제한 문제를 해결하고, LLM이 뉴스 데이터에 효율적으로 접근하여 사용자에게 정확하고 풍부한 정보를 제공할 수 있도록 했습니다.

## 🌟 주요 기능

* **뉴스 데이터 수집**: 네이버 뉴스 API를 통한 실시간 뉴스 기사 메타데이터 및 본문 크롤링.
* **한국어 텍스트 전처리**: `Konlpy`의 `Okt` 형태소 분석기를 이용한 정교한 텍스트 정제.
* **자동 토픽 분류**: `BERTopic` 모델을 활용하여 뉴스 기사를 주제별로 자동 분류하고, 각 토픽의 대표 키워드 및 이름을 추출.
* **데이터베이스 관리**: 수집 및 분석된 뉴스와 토픽 데이터를 MySQL에 체계적으로 저장.
* **FastMCP 서버 연동**: LLM이 뉴스 분석 데이터에 접근할 수 있는 다양한 도구(Tool) 제공.
    * **`get_available_analysis_dates()`**: 분석 완료된 날짜 목록 조회.
    * **`get_news_analysis_data()`**: 기간, 키워드, 토픽 ID 기반 뉴스 목록 조회 (핵심 정보만, 본문 제외).
    * **`get_article_content(article_id)`**: 특정 기사의 **원문 및 전처리된 텍스트** 조회.
    * **`get_topic_id_mapping(analysis_date)`**: 토픽 ID와 토픽 이름, 대표 키워드 매핑 조회.
    * **`get_latest_news_by_topic(topic_id)`**: 특정 토픽의 최신 뉴스 조회.
    * **`get_related_articles(article_id)`**: 특정 기사와 유사한 관련 기사 추천.
    * **`get_topic_keyword_frequency()`**: 특정 토픽의 주요 키워드 빈도 분석.
    * **`get_topic_trends()`**: 최근 N일간의 토픽 트렌드 분석.

## 💻 기술 스택

* **언어**: Python 3.9+
* **데이터베이스**: MySQL 8.0+
* **뉴스 수집 & 웹 크롤링**: `requests`, `BeautifulSoup4`
* **한국어 자연어 처리**: `Konlpy` (Okt)
* **텍스트 임베딩**: `Sentence Transformers`
* **토픽 모델링**: `BERTopic`
* **데이터 처리**: `Pandas`
* **DB 연동**: `PyMySQL`
* **MCP 서버**: `FastMCP`

## ⚙️ 시스템 아키텍처

[네이버 뉴스 API] --(수집)--> [daily_news_analyzer.py] --(전처리 & BERTopic 분석)--> [MySQL DB]
↑                                       ↓
└---------------------------------------┘
↓
[news_topic_mcp_server.py (FastMCP)]
↓
[LLM (e.g., Claude)]
↓
[사용자]


## 🛠️ 설치 및 실행 방법

### 1. 전제 조건

* Python 3.9 이상 설치
* MySQL 8.0 이상 설치 및 실행
* 네이버 개발자 센터에서 뉴스 검색 API 신청 및 `Client ID`, `Client Secret` 발급
    * `daily_news_analyzer.py` (또는 `new_news.py`) 파일 내에 `NAVER_CLIENT_ID` 와 `NAVER_CLIENT_SECRET` 변수를 본인의 키로 설정해주세요.

### 2. 데이터베이스 설정

1.  MySQL 서버에 접속하여 `news_analysis_db` 데이터베이스를 생성합니다.
    ```sql
    CREATE DATABASE news_analysis_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    ```
2.  `news_analysis_db`에 필요한 테이블을 생성합니다. (아래 스키마를 참고하여 직접 생성하거나, 프로젝트 내 `schema.sql` 파일이 있다면 해당 파일을 실행합니다.)

    **`news_articles` 테이블 스키마 예시:**
    ```sql
    CREATE TABLE news_articles (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(512) NOT NULL,
        link VARCHAR(512) NOT NULL UNIQUE,
        description TEXT,
        pub_date DATETIME,
        original_text LONGTEXT,
        processed_text LONGTEXT,
        analysis_date DATE NOT NULL,
        INDEX(analysis_date)
    );
    ```

    **`topic_info` 테이블 스키마 예시:**
    ```sql
    CREATE TABLE topic_info (
        id INT AUTO_INCREMENT PRIMARY KEY,
        analysis_date DATE NOT NULL,
        topic_id INT NOT NULL,
        topic_name VARCHAR(255),
        representation JSON,
        topic_count INT,
        UNIQUE (analysis_date, topic_id)
    );
    ```

    **`topic_results` 테이블 스키마 예시:**
    ```sql
    CREATE TABLE topic_results (
        id INT AUTO_INCREMENT PRIMARY KEY,
        article_id INT NOT NULL,
        topic_id INT NOT NULL,
        probability DOUBLE,
        analysis_date DATE NOT NULL,
        FOREIGN KEY (article_id) REFERENCES news_articles(id),
        INDEX(analysis_date, topic_id)
    );
    ```

### 3. 프로젝트 클론 및 의존성 설치

```bash
# GitHub에서 프로젝트 클론
git clone [https://github.com/your-username/your-repo-name.git](https://github.com/your-username/your-repo-name.git)
cd your-repo-name

# 가상 환경 생성 및 활성화 (권장)
python -m venv venv
# Windows
.\venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 필요한 라이브러리 설치
pip install -r requirements.txt
requirements.txt 파일 내용:

requests
beautifulsoup4
konlpy
bertopic
sentence-transformers
pandas
pymysql
pytz
fastmcp==0.1.0 # 설치된 FastMCP 버전에 따라 조정
4. 뉴스 데이터 수집 및 분석 (daily_news_analyzer.py)
매일 또는 주기적으로 실행하여 뉴스를 수집하고 분석합니다.

Bash

python daily_news_analyzer.py
(참고: 프로젝트의 메인 분석 스크립트가 new_news.py라면 해당 파일명으로 실행하세요.)

5. MCP 서버 실행 (news_topic_mcp_server.py)
LLM과의 연동을 위해 MCP 서버를 실행합니다.

Bash

python news_topic_mcp_server.py
서버가 성공적으로 실행되면, LLM 환경에서 이 서버를 도구로 활용할 수 있습니다.

🤝 기여 방법
프로젝트에 기여하고 싶으시다면 언제든지 환영합니다! Fork 후 Pull Request를 보내주세요.
이슈 보고 및 기능 제안도 환영합니다.

📄 라이선스
이 프로젝트는 MIT License를 따릅니다.

📞 문의
[Your Email Address]
[Your GitHub Profile URL]
<!-- end list -->
