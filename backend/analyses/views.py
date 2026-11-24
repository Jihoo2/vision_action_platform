"""분석 작업 API (DRF ModelViewSet)

  POST   /api/v1/analyses/              작업 생성 → PENDING, 작업 ID 즉시 반환
  GET    /api/v1/analyses/              내 작업 목록 (관리자는 전체)
  GET    /api/v1/analyses/{id}/         상세 + 사람별 예측
  PATCH  /api/v1/analyses/{id}/         제목·메모만 수정
  DELETE /api/v1/analyses/{id}/         삭제 (사람별 예측 CASCADE, 업로드 영상 파일도 삭제)
  GET    /api/v1/analyses/{id}/status/  상태만 가볍게 조회 (브라우저 주기 조회용)

다른 사용자의 작업은 get_queryset 단계에서 제외 → 존재 여부도 드러나지 않게 404 (T07)
"""
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AnalysisJob
from .tasks import run_analysis
from .serializers import (
    AnalysisJobCreateSerializer,
    AnalysisJobSerializer,
    AnalysisJobUpdateSerializer,
)


class AnalysisJobViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]   # PUT 전체 수정 금지

    def get_queryset(self):
        qs = AnalysisJob.objects.select_related("user").prefetch_related("predictions")
        user = self.request.user
        return qs if user.is_staff else qs.filter(user=user)

    def get_serializer_class(self):
        if self.action == "create":
            return AnalysisJobCreateSerializer
        if self.action == "partial_update":
            return AnalysisJobUpdateSerializer
        return AnalysisJobSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = serializer.save(user=request.user)            # status = PENDING
        # DB 커밋이 끝난 뒤에 Celery 작업 등록 → Worker가 아직 없는 Job을 찾는 일이 없음
        transaction.on_commit(lambda: enqueue_analysis(job.pk))
        return Response(AnalysisJobSerializer(job, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        job = self.get_object()
        serializer = self.get_serializer(job, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AnalysisJobSerializer(job, context={"request": request}).data)

    def perform_destroy(self, instance):
        if instance.video:
            instance.video.delete(save=False)                # media/ 의 실제 파일도 정리
        instance.delete()                                    # PersonPrediction 은 CASCADE

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        job = self.get_object()
        return Response({
            "id": job.id,
            "status": job.status,
            "status_display": job.get_status_display(),
            "done": job.status in (AnalysisJob.Status.COMPLETED, AnalysisJob.Status.FAILED),
            "prediction_count": job.predictions.count(),
            "result_message": job.result_message,
            "error_message": job.error_message,
        })


log = logging.getLogger(__name__)


def enqueue_analysis(job_id: int) -> None:
    """Redis 대기열에 작업 등록. Redis가 꺼져 있으면 FAILED 로 남겨 사용자가 알 수 있게 함"""
    try:
        result = run_analysis.delay(job_id)
        AnalysisJob.objects.filter(pk=job_id).update(celery_task_id=str(result.id))
    except Exception as e:  # noqa: BLE001
        log.exception("작업 등록 실패 job=%s", job_id)
        AnalysisJob.objects.filter(pk=job_id).update(
            status=AnalysisJob.Status.FAILED, finished_at=timezone.now(),
            error_message=f"작업 대기열(Redis)에 연결할 수 없습니다: {e.__class__.__name__}")
