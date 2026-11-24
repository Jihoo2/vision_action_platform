"""분석 업무 모델 2개 (회원은 Django 기본 auth_user 사용)

auth_user 1 ──< AnalysisJob 1 ──< PersonPrediction
  - 한 사용자는 여러 분석 작업을 요청할 수 있다.
  - 한 작업(영상 1개)에는 여러 사람(Track ID)의 예측이 저장될 수 있다.
  - track_id 는 '그 영상 안에서의' 추적 번호이며 영구적인 사람 ID가 아니다.
  - 영상 파일 자체는 media/ 에 두고 DB에는 경로만 저장한다.
"""
from django.conf import settings
from django.db import models


class Action(models.TextChoices):
    BEND_RETURN = "bend_return", "A001 허리 굽혔다 펴기"
    LEG_RAISE_LOWER = "leg_raise_lower", "A002 다리 들었다 내리기"
    WALK_TURN_WALK = "walk_turn_walk", "A003 걷다 방향 전환"
    DRINK_RETURN = "drink_return", "A004 마시고 원위치"
    SIT_STAND = "sit_stand", "A005 앉았다 일어나기"
    WAVE = "wave", "A006 손 흔들기"


class AnalysisJob(models.Model):
    class InputType(models.TextChoices):
        UPLOAD = "UPLOAD", "영상 업로드"
        IPCAM = "IPCAM", "IP Webcam"

    class Status(models.TextChoices):
        PENDING = "PENDING", "대기"
        PROCESSING = "PROCESSING", "처리 중"
        COMPLETED = "COMPLETED", "완료"
        FAILED = "FAILED", "실패"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="analysis_jobs", verbose_name="요청 사용자",
    )
    title = models.CharField("제목", max_length=100, blank=True)
    memo = models.TextField("메모", blank=True)

    input_type = models.CharField("입력 방식", max_length=10, choices=InputType.choices)
    video = models.FileField("영상 파일", upload_to="videos/%Y/%m/%d/", blank=True)
    camera_url = models.CharField("카메라 주소(허용 목록)", max_length=255, blank=True)
    capture_seconds = models.PositiveSmallIntegerField("수집 시간(초)", null=True, blank=True)
    expected_action = models.CharField(
        "사용자가 수행하려는 동작(정답 아님)", max_length=30,
        choices=Action.choices, blank=True,
    )

    status = models.CharField(
        "상태", max_length=12, choices=Status.choices,
        default=Status.PENDING, db_index=True,
    )
    celery_task_id = models.CharField("Celery Task ID", max_length=64, blank=True)
    error_message = models.TextField("오류 메시지", blank=True)
    result_message = models.CharField("분석 안내 메시지", max_length=255, blank=True)

    model_name = models.CharField("분석 모델", max_length=50, blank=True)    # 모델 교체 시 어떤 모델이 분석했는지 기록
    extra = models.JSONField("추가 정보", default=dict, blank=True)          # 제외된 Track·영상 정보 등 모델별 부가 정보

    video_duration_sec = models.FloatField("영상 길이(초)", null=True, blank=True)
    processing_time_sec = models.FloatField("AI 처리 시간(초)", null=True, blank=True)

    created_at = models.DateTimeField("생성 시각", auto_now_add=True)
    started_at = models.DateTimeField("처리 시작", null=True, blank=True)
    finished_at = models.DateTimeField("완료 시각", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "분석 작업"
        verbose_name_plural = "분석 작업"

    def __str__(self):
        return f"Job #{self.pk} {self.get_input_type_display()} [{self.status}]"


class PersonPrediction(models.Model):
    job = models.ForeignKey(
        AnalysisJob, on_delete=models.CASCADE,
        related_name="predictions", verbose_name="분석 작업",
    )
    track_id = models.IntegerField("Track ID(영상 내 추적 번호)")
    action_label = models.CharField("예측 동작", max_length=30, choices=Action.choices)
    confidence = models.FloatField("Confidence")
    second_label = models.CharField("2순위 동작", max_length=30, blank=True)
    second_confidence = models.FloatField("2순위 Confidence", null=True, blank=True)
    margin = models.FloatField("1·2순위 차이", null=True, blank=True)
    uncertain = models.BooleanField("판단 불확실", default=False)

    frames_seen = models.PositiveIntegerField("검출 Frame 수", default=0)
    window_count = models.PositiveSmallIntegerField("처리한 Window 수", default=1)
    valid_feature_ratio = models.FloatField("유효 Feature 비율", null=True, blank=True)
    mean_keypoint_conf = models.FloatField("평균 Keypoint 신뢰도", null=True, blank=True)
    extra = models.JSONField("모델별 추가 결과", default=dict, blank=True)   # 클래스별 확률, (교체 모델의) OK/NG·교정 메시지 등
    predicted_at = models.DateTimeField("예측 시각", auto_now_add=True)

    class Meta:
        ordering = ["job", "track_id"]
        constraints = [
            models.UniqueConstraint(fields=["job", "track_id"], name="uniq_job_track"),
        ]
        verbose_name = "사람별 예측"
        verbose_name_plural = "사람별 예측"

    def __str__(self):
        return f"Job #{self.job_id} · Track {self.track_id} → {self.action_label} ({self.confidence:.2f})"
