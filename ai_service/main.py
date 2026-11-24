"""Vision Action AI 추론 서버 (FastAPI)

실행:  cd ai_service && uvicorn main:app --host 0.0.0.0 --port 8001
문서:  http://localhost:8001/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from routers import predictions
from services.model_loader import get_bundle, load_models


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_models()          # 서버 시작 시 1회만 로드 → 이후 요청에서 재사용
    yield


app = FastAPI(title="Vision Action AI Service", version="1.0.0", lifespan=lifespan)
app.include_router(predictions.router)


@app.get("/health", tags=["health"])
def health():
    b = get_bundle()
    if b is None:
        return {"status": "starting", "model_loaded": False}
    return {
        "status": "ok" if b.ready else "error",
        "model_loaded": b.ready,
        "checks": b.checks,
        "n_features": int(b.rf.n_features_in_),
        "classes": b.classes,
        "sequence_steps": b.sequence_steps,
        "device": b.device,
    }
