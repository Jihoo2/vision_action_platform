"""팀 자세 판정 AI 서버 (FastAPI) — Vision Action Platform 의 두 번째 AI 서비스

  GET  /health            엔진·Pose 모델·판정 기준 파일 상태
  POST /api/v1/judge/     영상 + 동작(A001/A004/A008) + 각도(auto/front/diag/side) → 회차별 OK/NG/CHECK

응답 코드 규칙은 ai_service 와 같습니다 (Django services.py 가 그대로 처리).
  200 정상 / 200 + 빈 reps (사람·회차 없음) / 400 입력 오류 / 422 손상 영상 / 503 엔진 미준비
"""
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from engine import ACTIONS, MODEL_NAME, TEAM_DIR, VIEWS, TeamEngine, VideoReadError

ALLOWED_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_SECONDS = float(os.getenv("FORM_MAX_SECONDS", "120"))
engine = TeamEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine.load()            # 팀 엔진 + YOLO 를 서버 시작 때 한 번만
    yield


app = FastAPI(title="team05 form judge (Vision Action Platform)", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok" if engine.ready else "error", "model_loaded": engine.ready,
            "model": MODEL_NAME, "team_dir": str(TEAM_DIR), "error": engine.error,
            "actions": ACTIONS, "artifacts": engine.artifacts()}


@app.post("/api/v1/judge/")
async def judge(file: UploadFile = File(...), action: str = Form(...), view: str = Form("auto")):
    if not engine.ready:
        raise HTTPException(503, f"판정 엔진이 준비되지 않았습니다: {engine.error}")
    if action not in ACTIONS:
        raise HTTPException(400, f"판정할 수 없는 동작입니다: {action} (가능: {', '.join(ACTIONS)})")
    if view not in VIEWS:
        raise HTTPException(400, f"촬영 각도 값 오류: {view}")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"지원하지 않는 형식입니다: {ext or '확장자 없음'}")
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = await run_in_threadpool(engine.judge_video, tmp_path, action, view, MAX_SECONDS)
    except VideoReadError as e:
        raise HTTPException(422, str(e)) from e
    finally:
        os.unlink(tmp_path)
    return {"ok": True, "filename": file.filename,
            "model": {"name": MODEL_NAME, "kind": "rules+form_model", "action": action},
            **result}
