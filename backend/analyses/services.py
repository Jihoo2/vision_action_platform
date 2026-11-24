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
    """6개 동작 인식 (ai_service)"""
    url = f"{settings.FASTAPI_URL.rstrip('/')}/api/v1/predict/"
    return _post(url, video_path, settings.FASTAPI_TIMEOUT_SEC, "AI 서버")


def judge_form(video_path: str, exercise: str, view: str = "auto") -> dict:
    """팀 자세 판정 (form_service) — 응답 코드 규칙은 predict_video 와 같음"""
    url = f"{settings.FORM_SERVICE_URL.rstrip('/')}/api/v1/judge/"
    return _post(url, video_path, settings.FORM_TIMEOUT_SEC, "자세 판정 AI 서버",
                 data={"action": exercise, "view": view or "auto"})


def _post(url: str, video_path: str, timeout: float, who: str, data: dict | None = None) -> dict:
    path = Path(video_path)
    try:
        with path.open("rb") as f:
            res = httpx.post(url, files={"file": (path.name, f, "video/mp4")}, data=data or {},
                             timeout=timeout)
    except FileNotFoundError as e:
        raise AIInputError("분석할 영상 파일을 찾을 수 없습니다.") from e
    except httpx.TimeoutException as e:
        raise AIServiceError(f"{who} 응답 시간 초과 ({timeout:.0f}초)") from e
    except httpx.HTTPError as e:
        raise AIServiceError(f"{who}에 연결할 수 없습니다: {e.__class__.__name__}") from e

    if res.status_code in (400, 422):
        raise AIInputError(_detail(res))
    if res.status_code >= 400:
        raise AIServiceError(f"{who} 오류 {res.status_code}: {_detail(res)}")
    return res.json()


def _detail(res: httpx.Response) -> str:
    try:
        return str(res.json().get("detail", res.text))[:300]
    except ValueError:
        return res.text[:300]
