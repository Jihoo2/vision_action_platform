"""FastAPI AI 추론 서버 호출 (HTTP)

FastAPI 응답 규칙(ai_service/routers/predictions.py)에 맞춰 오류를 두 종류로 나눕니다.
  AIInputError    : 영상 자체 문제 (400 너무 짧음/형식, 422 손상)  → 사용자에게 사유 표시
  AIServiceError  : 서버 문제 (연결 실패, 타임아웃, 5xx, 503 모델 미준비)
"""
from pathlib import Path

import httpx
from django.conf import settings


class AIInputError(Exception):
    pass


class AIServiceError(Exception):
    pass


def predict_video(video_path: str) -> dict:
    url = f"{settings.FASTAPI_URL.rstrip('/')}/api/v1/predict/"
    path = Path(video_path)
    try:
        with path.open("rb") as f:
            res = httpx.post(url, files={"file": (path.name, f, "video/mp4")},
                             timeout=settings.FASTAPI_TIMEOUT_SEC)
    except FileNotFoundError as e:
        raise AIInputError("분석할 영상 파일을 찾을 수 없습니다.") from e
    except httpx.TimeoutException as e:
        raise AIServiceError(f"AI 서버 응답 시간 초과 ({settings.FASTAPI_TIMEOUT_SEC:.0f}초)") from e
    except httpx.HTTPError as e:
        raise AIServiceError(f"AI 서버에 연결할 수 없습니다: {e.__class__.__name__}") from e

    if res.status_code in (400, 422):
        raise AIInputError(_detail(res))
    if res.status_code >= 400:
        raise AIServiceError(f"AI 서버 오류 {res.status_code}: {_detail(res)}")
    return res.json()


def _detail(res: httpx.Response) -> str:
    try:
        return str(res.json().get("detail", res.text))[:300]
    except ValueError:
        return res.text[:300]
