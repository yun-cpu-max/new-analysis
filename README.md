# 📰 AI 기반 뉴스 토픽 분석 시스템

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg?logo=python&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0+-blue.svg?logo=mysql&logoColor=white)
![n8n](https://img.shields.io/badge/n8n-Workflow-orange.svg?logo=n8n&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-lightgrey.svg)
![Claude](https://img.shields.io/badge/Claude-AI%20Model-purple.svg?logo=openai&logoColor=white)

## 🚀 프로젝트 개요

본 프로젝트는 뉴스 데이터를 자동으로 수집, 분석하여 주요 토픽을 식별하고, 이를 Claude와 같은 대규모 언어 모델(LLM)이 활용할 수 있는 MCP(Model Context Protocol) 서버 형태로 제공하는 시스템입니다. 사용자는 자연어 질의를 통해 최신 뉴스 트렌드 및 특정 주제에 대한 심층 분석 정보를 얻을 수 있습니다.

### 주요 기능

* **자동 뉴스 데이터 수집:** n8n 워크플로우를 통해 네이버 뉴스 API에서 뉴스 데이터를 주기적으로 수집합니다.
* **텍스트 전처리 및 토픽 모델링:** 수집된 뉴스 기사에 대해 텍스트 전처리(형태소 분석, 불용어 제거)를 수행하고, LDA(Latent Dirichlet Allocation)를 이용하여 주요 토픽을 식별합니다.
* **MySQL 데이터베이스 연동:** 수집된 원본 뉴스 데이터와 분석된 토픽 정보를 MySQL 데이터베이스에 저장 및 관리합니다.
* **MCP 서버를 통한 AI 연동:** `mcp` 라이브러리(FastMCP)를 사용하여 LLM(예: Claude)이 접근할 수 있는 도구(Tools)를 제공합니다.
* **뉴스 분석 도구:** 다음 기능을 포함한 도구들을 LLM에게 제공하여 다양한 질의에 응답합니다:
    * 분석 가능한 날짜 목록 조회
    * 기간/키워드/토픽 ID 기반 뉴스 기사 검색
    * 특정 토픽의 키워드 빈도 분석
    * 최근 토픽 트렌드 조회

## 🛠️ 기술 스택

* **데이터 수집/오케스트레이션:** n8n
* **데이터베이스:** MySQL
* **백엔드/분석:** Python 3.11+
    * `pymysql`: MySQL 데이터베이스 연동
    * `konlpy`: 한국어 형태소 분석
    * `gensim`: LDA 토픽 모델링
    * `requests`: 웹 요청 (뉴스 API)
    * `beautifulsoup4`: HTML 파싱 (필요 시)
    * `mcp`: Model Context Protocol 서버 구축 (`FastMCP`)
* **LLM 연동:** Claude (via Claude Desktop)

## 📦 설치 및 설정

### 1. MySQL 데이터베이스 설정

1.  MySQL 서버를 설치하고 실행합니다.
2.  새 데이터베이스 `news_analysis_db`를 생성합니다.
    ```sql
    CREATE DATABASE news_analysis_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    ```
3.  `news_analysis_db`에 접근할 사용자(`root` 또는 다른 사용자)의 비밀번호를 설정하거나 확인합니다. (`mysql@24!`는 예시 비밀번호)
4.  다음 SQL 스키마를 실행하여 필요한 테이블을 생성합니다. (스키마는 `daily_news_analyzer.py` 또는 별도의 SQL 파일에 정의되어 있을 수 있습니다.)

    ```sql
    -- news_articles 테이블
    CREATE TABLE IF NOT EXISTS news_articles (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title TEXT NOT NULL,
        link VARCHAR(512) NOT NULL UNIQUE,
        description TEXT,
        pub_date DATETIME,
        original_text LONGTEXT,
        processed_text LONGTEXT,
        analysis_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- topic_info 테이블
    CREATE TABLE IF NOT EXISTS topic_info (
        id INT AUTO_INCREMENT PRIMARY KEY,
        analysis_date DATE NOT NULL,
        topic_id INT NOT NULL,
        topic_name VARCHAR(255),
        topic_count INT,
        representation JSON, -- JSON 형태의 토픽 키워드
        UNIQUE (analysis_date, topic_id)
    );

    -- topic_results 테이블 (기사와 토픽 연결)
    CREATE TABLE IF NOT EXISTS topic_results (
        id INT AUTO_INCREMENT PRIMARY KEY,
        article_id INT NOT NULL,
        analysis_date DATE NOT NULL, -- 토픽 분석이 수행된 날짜
        topic_id INT NOT NULL,
        probability DOUBLE NOT NULL,
        FOREIGN KEY (article_id) REFERENCES news_articles(id) ON DELETE CASCADE,
        FOREIGN KEY (topic_id, analysis_date) REFERENCES topic_info(topic_id, analysis_date) ON DELETE CASCADE,
        UNIQUE (article_id, topic_id) -- 한 기사가 여러 토픽에 속할 수 있지만, 같은 토픽에 중복 할당 방지
    );
    ```

### 2. Python 환경 설정

1.  Python 3.11 이상이 설치되어 있는지 확인합니다.
2.  프로젝트 디렉토리로 이동하여 필요한 라이브러리를 설치합니다.
    ```bash
    pip install pymysql konlpy gensim requests beautifulsoup4 mcp
    ```
3.  `news_topic_mcp_server.py` 파일 내의 MySQL 연결 정보를 환경에 맞게 수정합니다.
    ```python
    MYSQL_HOST = "localhost"
    MYSQL_USER = "root"
    MYSQL_PASSWORD = "mysql@24!" # 실제 비밀번호로 변경
    MYSQL_DB = "news_analysis_db"
    ```

### 3. n8n 워크플로우 설정

1.  n8n을 설치하고 실행합니다. (Docker 또는 NPM)
2.  n8n UI에 접속하여 새 워크플로우를 생성합니다.
3.  **네이버 뉴스 API 노드:**
    * 네이버 개발자 센터에서 뉴스 API 키(Client ID, Client Secret)를 발급받습니다.
    * n8n에서 HTTP Request 또는 Custom Code 노드를 사용하여 네이버 뉴스 API를 호출하도록 설정합니다.
    * 쿼리 파라미터(예: `query`, `display`, `sort`)를 설정합니다.
4.  **MySQL 노드:**
    * 수집된 데이터를 MySQL 데이터베이스의 `news_articles` 테이블에 삽입하도록 설정합니다. 중복 방지를 위해 `link` 필드의 `UNIQUE` 제약 조건을 활용하는 것이 좋습니다.
5.  **스케줄 트리거:** `Cron` 노드 등을 사용하여 워크플로우가 주기적으로(예: 매일 자정) 실행되도록 설정합니다.

### 4. `daily_news_analyzer.py` 실행

* 수집된 뉴스 데이터를 분석하고 토픽 모델링을 수행합니다. 이 스크립트는 MySQL 데이터베이스에서 원문 텍스트를 읽어와 `processed_text`, `topic_results`, `topic_info` 테이블을 업데이트합니다.
* 이 스크립트는 n8n 워크플로우의 후처리 단계에서 실행되거나, 별도의 스케줄러(예: Windows 작업 스케줄러, Linux cron)에 의해 주기적으로 실행될 수 있습니다.

### 5. MCP 서버 실행 및 Claude Desktop 연동

1.  `news_topic_mcp_server.py`를 실행합니다.
    ```bash
    python news_topic_mcp_server.py
    ```
    서버가 성공적으로 실행되면 터미널에 "FastMCP 서버 초기화 완료, 클라이언트 연결 대기 중..."과 같은 메시지가 표시됩니다.

2.  **Claude Desktop 설정:**
    * Claude Desktop 애플리케이션을 실행합니다.
    * `claude_desktop_config.json` 파일을 찾아 편집합니다. (일반적으로 `C:\Users\<사용자이름>\AppData\Roaming\Claude Desktop\config.json` 또는 유사한 경로에 위치)
    * `mcpServers` 섹션에 `news_analyzer` 항목을 다음과 같이 추가합니다. `command` 경로는 `python.exe`의 실제 경로로, `args`의 경로는 `news_topic_mcp_server.py` 파일의 실제 경로로 변경해야 합니다.

        ```json
        {
          "mcpServers": {
            // ... 다른 서버 설정들 (weather, filesystem 등)
            "news_analyzer": {
              "command": "C:\\Users\\<사용자이름>\\AppData\\Local\\Programs\\Python\\Python311\\python.exe", // 실제 Python 경로
              "args": ["C:\\Users\\<사용자이름>\\Desktop\\mcp_servers\\news_topic_mcp_server.py"] // 실제 파일 경로
            }
          }
        }
        ```
    * 파일을 저장하고 Claude Desktop을 완전히 종료했다가 다시 시작합니다.
    * Claude Desktop의 "MCP 설정 열기"를 통해 `news_analyzer` 서버가 "Connected" 또는 "활성화됨" 상태인지 확인합니다.

## 💡 사용 방법 (Claude를 통해)

MCP 서버가 성공적으로 연결되면 Claude에게 자연어 질의를 통해 뉴스 분석 정보를 요청할 수 있습니다.

**예시 질의:**

* "오늘 뉴스 기사 중 가장 중요한 토픽은 무엇이고, 어떤 키워드들이 있나요?"
* "2024년 6월 10일의 5번 토픽에 대한 키워드 분석 결과를 알려줘." (토픽 ID는 Claude가 `get_news_analysis_data` 등을 통해 파악할 수 있습니다.)
* "지난 7일간의 주요 경제 뉴스 트렌드를 요약해 줘."
* "2024년 5월 1일부터 5월 31일까지의 '인공지능' 관련 뉴스를 검색해 줘."
* "분석 가능한 뉴스 날짜 목록을 알려줘."

## 🤝 기여 방법

* 이슈 보고 및 기능 제안 환영합니다.
* 풀 리퀘스트를 통한 코드 기여도 환영합니다.

## 📄 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.
