# 팀 자세 판정 AI 서버 — 팀 코드(G5_skeleton/subject10_team_pilot)는 이미지에 넣지 않고 /team 볼륨으로 연결
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    YOLO_CONFIG_DIR=/tmp/ultralytics \
    TEAM_DIR=/team \
    POSE_MODEL=/app/models/yolo11n-pose.pt

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# torch 와 torchvision 은 같은 CPU 저장소에서 함께 (ai_service 에서 겪은 nms 오류 방지)
RUN pip install torch==2.15.0 torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

COPY . .
EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
