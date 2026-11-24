# FastAPI AI 추론 서버 (YOLO Pose + 6일차 Random Forest)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    YOLO_CONFIG_DIR=/tmp/ultralytics

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# 컨테이너는 CPU로 추론 (GPU 컨테이너는 NVIDIA Container Toolkit 이 따로 필요)
# → CPU 전용 torch 를 먼저 설치해 이미지 크기를 줄임. 나머지는 학습 환경과 같은 버전.
RUN pip install torch==2.15.0 torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

COPY . .
# 학습 산출물·Pose 가중치(models/)는 이미지에 넣지 않고 compose 에서 읽기 전용으로 연결
EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
