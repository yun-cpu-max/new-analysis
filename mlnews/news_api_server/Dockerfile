# Python 베이스 이미지
FROM python:3.9-slim

# 작업 디렉토리 설정
WORKDIR /app

# 로컬 파일 복사
COPY . /app

# Java 설치 (konlpy를 위해 필요)
RUN apt-get update && \
    apt-get install -y default-jdk && \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# 컨테이너 외부에서 접근 가능하도록 포트 열기
EXPOSE 5000

# 서버 실행
CMD ["python", "app.py"]
