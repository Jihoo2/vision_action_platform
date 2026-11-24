"""Celery 작업: 분석 1건 처리 — AI 분석 파이프라인의 중심

run_analysis(job_id)                         ← views.enqueue_analysis 가 Redis 로 보낸 작업
  ① PENDING → PROCESSING (조건부 UPDATE, 중복 실행 방지)
  ② _acquire_video()      업로드 경로 / 웹캠 수집 (camera_capture.py)
  ③ AI 서버 호출           ACTION → services.predict_video → ai_service :8001
                           FORM   → services.judge_form    → form_service :8002
  ④ 결과 저장              _save_predictions() / _save_reps() → _complete()  ⇒ COMPLETED
     어디서든 예외          _fail()  ⇒ FAILED + 사유
FastAPI는 JSON만 반환하고, DB 저장은 여기(Worker)에서 Django ORM으로 합니다.
"""
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .camera_capture import CameraError, capture_clip
from .models import AnalysisJob, PersonPrediction, RepJudgment
from .services import AIInputError, AIServiceError, judge_form, predict_video

log = logging.getLogger(__name__)
# AI 응답 중 PersonPrediction 의 '칸'으로 저장하는 값 (나머지는 extra JSON)
PRED_FIELDS = ["track_id", "action_label", "confidence", "second_label", "second_confidence",
               "margin", "uncertain", "frames_seen", "window_count",
               "valid_feature_ratio", "mean_keypoint_conf"]
# 팀 판정 이벤트 중 RepJudgment.extra 에 남기는 값 (측정값·기준 등)
REP_EXTRA_FIELDS = ("checks", "values", "view", "depth", "knee_min", "start_frame", "end_frame")


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
    # ① 같은 작업이 두 번 실행되지 않도록 PENDING 일 때만 PROCESSING 으로 바꿈
    updated = AnalysisJob.objects.filter(pk=job_id, status=AnalysisJob.Status.PENDING).update(
        status=AnalysisJob.Status.PROCESSING, started_at=timezone.now(),
        celery_task_id=self.request.id or "")
    if not updated:
        log.warning("Job %s: PENDING 상태가 아니어서 건너뜀", job_id)
        return {"job_id": job_id, "skipped": True}

    job = AnalysisJob.objects.get(pk=job_id)
    log.info("Job %s 처리 시작 (%s · %s)", job_id, job.task_type, job.input_type)
    try:
        video_path = _acquire_video(job)                # ② 영상 확보
        # ③ 어느 AI 서버로 보낼지 — 분석 종류(task_type) 하나로 결정
        if job.task_type == AnalysisJob.TaskType.FORM:      # 팀 자세 판정 (form_service)
            result = judge_form(video_path, job.exercise, job.camera_view)
        else:                                               # 6개 동작 인식 (ai_service)
            result = predict_video(video_path)
    except (CameraError, AIInputError, AIServiceError) as e:
        return _fail(job, str(e))
    except Exception as e:  # noqa: BLE001  예상 못 한 오류도 FAILED 로 남김
        log.exception("Job %s 예외", job_id)
        return _fail(job, f"처리 중 오류: {e.__class__.__name__}: {e}")

    # ③ 결과 저장 — 저장 모양만 다르고, 완료 처리는 _complete() 한 곳
    if job.task_type == AnalysisJob.TaskType.FORM:
        return _save_reps(job, result)
    return _save_predictions(job, result)


def _save_predictions(job: AnalysisJob, result: dict) -> dict:
    """동작 인식(ai_service) 결과 → 사람별 PersonPrediction"""
    with transaction.atomic():
        job.predictions.all().delete()                  # 재실행돼도 중복 없음
        PersonPrediction.objects.bulk_create([
            PersonPrediction(
                job=job,
                extra={k: v for k, v in p.items() if k not in PRED_FIELDS},   # probabilities 등
                **{k: p.get(k) for k in PRED_FIELDS if p.get(k) is not None})
            for p in result.get("predictions", [])
        ])
        _complete(job, result,
                  extra={"schema": "action.v1", "video": result.get("video"),
                         "skipped_tracks": result.get("skipped_tracks", []), "model": result.get("model")},
                  duration=(result.get("video") or {}).get("duration_sec"))
    n = job.predictions.count()
    log.info("Job %s 완료: 예측 %d건", job.pk, n)
    return {"job_id": job.pk, "status": job.status, "predictions": n}


def _save_reps(job: AnalysisJob, result: dict) -> dict:
    """자세 판정(form_service) 결과 → 회차별 RepJudgment"""
    meta, summary = result.get("meta") or {}, result.get("summary") or {}
    with transaction.atomic():
        job.reps.all().delete()
        RepJudgment.objects.bulk_create([
            RepJudgment(
                job=job, seq=i, rep_label=str(e.get("rep", i))[:12], kind=e.get("kind") or "rep",
                verdict=e.get("verdict") or "CHECK",
                start_sec=e.get("start_s"), end_sec=e.get("end_s"),
                message=(e.get("message") or "")[:255],
                out_of_range=(e.get("out_of_range") or "")[:255],
                boundary=(e.get("boundary") or "")[:255],
                model_flag=bool(e.get("model_flag")), model_score=e.get("model_score"),
                extra={k: e.get(k) for k in REP_EXTRA_FIELDS if e.get(k) is not None})
            for i, e in enumerate(result.get("reps", []), start=1)
        ])
        _complete(job, result,
                  extra={"schema": "form.v1", "meta": meta, "summary": summary, "model": result.get("model")},
                  duration=meta.get("duration_sec"))
    n = job.reps.count()
    log.info("Job %s 자세 판정 완료: %d건 %s", job.pk, n, summary)
    return {"job_id": job.pk, "status": job.status, "reps": n}


def _complete(job: AnalysisJob, result: dict, *, extra: dict, duration) -> None:
    """두 AI 서버 공통 완료 처리 — 모델 이름·요약·시간·COMPLETED (호출하는 쪽 트랜잭션 안에서)"""
    job.model_name = (result.get("model") or {}).get("name", "")[:50]
    job.extra = extra
    job.status = AnalysisJob.Status.COMPLETED
    job.result_message = (result.get("message") or "")[:255]
    job.error_message = ""
    job.video_duration_sec = duration
    job.processing_time_sec = result.get("processing_time_sec")
    job.finished_at = timezone.now()
    job.save()


def _fail(job: AnalysisJob, message: str):
    job.status = AnalysisJob.Status.FAILED
    job.error_message = message[:1000]
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error_message", "finished_at"])
    log.warning("Job %s 실패: %s", job.pk, message)
    return {"job_id": job.pk, "status": job.status, "error": message}
