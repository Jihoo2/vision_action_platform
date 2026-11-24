"""HTML 화면 (DRF API를 브라우저 JavaScript가 호출하는 구조)

/analyses/   사용자 분석 화면: 업로드/IP Webcam 선택 → 분석 시작 → 상태·결과·최근 이력
/dashboard/  관리자 전용 통계 화면 (10단계)
"""
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from .models import Action


def _camera_label(i: int, url: str) -> str:
    port = urlparse(url).port or ""
    return f"허용 카메라 {i + 1} (:{port})"      # 화면·캡처에 내부 IP가 그대로 보이지 않게


@login_required
@ensure_csrf_cookie                              # fetch(POST)에 쓸 CSRF 쿠키 보장
def analyses_index(request):
    return render(request, "analyses/index.html", {
        "actions": Action.choices,
        "cameras": [(url, _camera_label(i, url)) for i, url in enumerate(settings.ALLOWED_CAMERA_URLS)],
        "capture_seconds": settings.CAMERA_CAPTURE_SECONDS,
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        "allowed_ext": ", ".join(settings.ALLOWED_VIDEO_EXTENSIONS),
    })


# ---------------------------------------------------------------- 10단계: 관리자 대시보드
from django.core.exceptions import PermissionDenied  # noqa: E402
from django.db.models import Avg, Count  # noqa: E402

from .models import AnalysisJob, PersonPrediction  # noqa: E402


@login_required
def dashboard(request):
    """관리자 전용. 숫자는 모두 PostgreSQL을 Django ORM으로 집계 (FastAPI는 DB에 접근하지 않음)"""
    if not request.user.is_staff:
        raise PermissionDenied("관리자만 접근할 수 있습니다.")

    action_names = dict(Action.choices)
    status_names = dict(AnalysisJob.Status.choices)
    input_names = dict(AnalysisJob.InputType.choices)

    # 차트 1: 동작별 예측 건수 — 6개 동작은 0건이어도 표시, 모델 교체로 새 라벨이 생기면 자동 추가
    by_action = dict(PersonPrediction.objects.values_list("action_label").annotate(n=Count("id")))
    action_keys = list(action_names) + sorted(k for k in by_action if k not in action_names)
    # 차트 2: 작업 상태별 건수
    by_status = dict(AnalysisJob.objects.values_list("status").annotate(n=Count("id")))
    # 선택: 입력 방식별 건수
    by_input = dict(AnalysisJob.objects.values_list("input_type").annotate(n=Count("id")))

    chart = {
        "actions": {"labels": [action_names.get(k, k) for k in action_keys],
                    "values": [by_action.get(k, 0) for k in action_keys]},
        "status": {"labels": [status_names[k] for k in AnalysisJob.Status.values],
                   "values": [by_status.get(k, 0) for k in AnalysisJob.Status.values]},
        "input": {"labels": [input_names[k] for k in AnalysisJob.InputType.values],
                  "values": [by_input.get(k, 0) for k in AnalysisJob.InputType.values]},
    }
    summary = {
        "jobs": AnalysisJob.objects.count(),
        "predictions": PersonPrediction.objects.count(),
        "users": AnalysisJob.objects.values("user").distinct().count(),
        "uncertain": PersonPrediction.objects.filter(uncertain=True).count(),
        "avg_processing": AnalysisJob.objects.filter(status=AnalysisJob.Status.COMPLETED)
                                             .aggregate(v=Avg("processing_time_sec"))["v"],
    }
    recent = (AnalysisJob.objects.select_related("user")
              .annotate(pred_count=Count("predictions")).order_by("-created_at")[:10])
    return render(request, "analyses/dashboard.html",
                  {"chart": chart, "summary": summary, "recent": recent})
