"""POST /api/v1/predict/ — Celery Worker(또는 Swagger)가 보낸 영상 1개를 분석해 JSON으로 반환

응답 규칙 (Worker가 상황을 구분하는 기준)
  200 + predictions 있음      : 정상 분석
  200 + predictions 빈 목록   : 영상은 정상, 사람 없음/관절 부족 → message 에 사유
  400                         : 파일 없음·확장자 오류·영상이 너무 짧음
  422                         : 손상된 영상 (열 수 없음·Frame 없음)
  503                         : 모델이 아직 준비되지 않음
FastAPI는 DB에 저장하지 않습니다. 저장은 Celery Worker가 Django ORM으로 합니다.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from services.action_inference import predict_video
from services.model_loader import get_bundle
from services.pose_pipeline import VideoReadError, extract_tracks

router = APIRouter(prefix="/api/v1", tags=["predict"])

ALLOWED_EXT = {".mp4", ".mov", ".avi", ".mkv"}
MIN_DURATION_SEC = float(os.getenv("MIN_VIDEO_SECONDS", "1.0"))
MAX_DURATION_SEC = float(os.getenv("MAX_VIDEO_SECONDS", "60"))


def _analyze(path: str):
    bundle = get_bundle()
    video = extract_tracks(path, bundle, max_seconds=MAX_DURATION_SEC)
    return video, predict_video(video, bundle)


@router.post("/predict/")
async def predict(file: UploadFile = File(..., description="분석할 영상 (mp4 권장)")):
    bundle = get_bundle()
    if bundle is None or not bundle.ready:
        raise HTTPException(503, "모델이 준비되지 않았습니다.")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"지원하지 않는 형식입니다: {ext or '(확장자 없음)'} — {sorted(ALLOWED_EXT)}")

    started = time.perf_counter()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        video, result = await run_in_threadpool(_analyze, tmp_path)
    except VideoReadError as e:
        raise HTTPException(422, str(e)) from e
    finally:
        os.unlink(tmp_path)

    if video.duration_sec < MIN_DURATION_SEC:
        raise HTTPException(400, f"영상이 너무 짧습니다 ({video.duration_sec:.1f}초). "
                                 f"{MIN_DURATION_SEC:.0f}초 이상 촬영해 주세요.")

    return {
        "ok": True,
        "filename": file.filename,
        "video": {"frames": video.frames, "fps": round(video.fps, 2),
                  "duration_sec": round(video.duration_sec, 2),
                  "width": video.width, "height": video.height},
        "model": {"name": "rf_action_baseline", "classes": bundle.classes,
                  "sequence_steps": bundle.sequence_steps, "method": "clip"},
        **result,
        "processing_time_sec": round(time.perf_counter() - started, 2),
    }
