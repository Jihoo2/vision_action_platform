"""Celery 작업: 분석 1건 처리

PENDING → PROCESSING → (영상 확보 → FastAPI 추론 → ORM 저장) → COMPLETED / FAILED
FastAPI는 JSON만 반환하고, DB 저장은 여기(Worker)에서 Django ORM으로 합니다.
"""
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .camera_capture import CameraError, capture_clip
from .models import AnalysisJob, PersonPrediction
from .services import AIInputError, AIServiceError, predict_video

log = logging.getLogger(__name__)
PRED_FIELDS = ["track_id", "action_label", "confidence", "second_label", "second_confidence",
               "margin", "uncertain", "frames_seen", "window_count",
               "valid_feature_ratio", "mean_keypoint_conf"]


def _acquire_video(job: AnalysisJob) -> str:
    """분석할 영상의 실제 경로. IP Webcam이면 여기서 N초 수집 후 job.video 에 저장"""
    if job.input_type == AnalysisJob.InputType.IPCAM:
        rel_path, info = capture_clip(job.camera_url, job.capture_seconds or 8, job.pk)
        job.video.name = rel_path                       # 수집 영상도 업로드 영상처럼 경로를 DB에 기록
        job.save(update_fields=["video"])
        log.info("Job %s 카메라 수집 완료: %s", job.pk, info)
    return job.video.path


@shared_task(bind=True)
def run_analysis(self, job_id: int):
    # 같은 작업이 두 번 실행되지 않도록 PENDING 일 때만 PROCESSING 으로 바꿈
    updated = AnalysisJob.objects.filter(pk=job_id, status=AnalysisJob.Status.PENDING).update(
        status=AnalysisJob.Status.PROCESSING, started_at=timezone.now(),
        celery_task_id=self.request.id or "")
    if not updated:
        log.warning("Job %s: PENDING 상태가 아니어서 건너뜀", job_id)
        return {"job_id": job_id, "skipped": True}

    job = AnalysisJob.objects.get(pk=job_id)
    log.info("Job %s 처리 시작 (%s)", job_id, job.input_type)
    try:
        video_path = _acquire_video(job)
        result = predict_video(video_path)
    except (CameraError, AIInputError, AIServiceError) as e:
        return _fail(job, str(e))
    except Exception as e:  # noqa: BLE001  예상 못 한 오류도 FAILED 로 남김
        log.exception("Job %s 예외", job_id)
        return _fail(job, f"처리 중 오류: {e.__class__.__name__}: {e}")

    with transaction.atomic():
        job.predictions.all().delete()
        PersonPrediction.objects.bulk_create([
            PersonPrediction(
                job=job,
                extra={k: v for k, v in p.items() if k not in PRED_FIELDS and k != "track_id"} | {},
                **{k: p.get(k) for k in PRED_FIELDS if p.get(k) is not None})
            for p in result.get("predictions", [])
        ])
        job.model_name = (result.get("model") or {}).get("name", "")[:50]
        job.extra = {"video": result.get("video"), "skipped_tracks": result.get("skipped_tracks", []),
                     "model": result.get("model")}
        job.status = AnalysisJob.Status.COMPLETED
        job.result_message = (result.get("message") or "")[:255]
        job.error_message = ""
        job.video_duration_sec = (result.get("video") or {}).get("duration_sec")
        job.processing_time_sec = result.get("processing_time_sec")
        job.finished_at = timezone.now()
        job.save()
    log.info("Job %s 완료: 예측 %d건", job_id, job.predictions.count())
    return {"job_id": job_id, "status": job.status, "predictions": job.predictions.count()}


def _fail(job: AnalysisJob, message: str):
    job.status = AnalysisJob.Status.FAILED
    job.error_message = message[:1000]
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error_message", "finished_at"])
    log.warning("Job %s 실패: %s", job.pk, message)
    return {"job_id": job.pk, "status": job.status, "error": message}
