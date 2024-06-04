# 베이스 이미지 지정
FROM python:3.11

# 작업 디렉토리 설정
WORKDIR /app

# 필요한 패키지와 curl 설치
RUN apt-get update && \
    apt-get install -y curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir fastapi uvicorn httpx


# 애플리케이션 파일 복사
COPY . .

# 호스트와 컨테이너 간에 포트 매핑
EXPOSE 11003

