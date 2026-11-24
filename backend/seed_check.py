"""3단계 수동 검증용: ORM으로 작업 1건 + 사람별 예측 2건 생성 후 조회
실행: python manage.py shell < seed_check.py
(2단계 FastAPI의 SBU 포옹 응답을 그대로 옮긴 값 — 작업 1건에 결과 2건 연결 확인)
"""
from django.contrib.auth import get_user_model

from analyses.models import AnalysisJob, PersonPrediction

User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
job = AnalysisJob.objects.create(user=user, title="3단계 ORM 확인", input_type="UPLOAD",
                                 status="COMPLETED", video_duration_sec=2.16,
                                 result_message="일부 결과는 1·2순위 차이가 작아 판단이 불확실합니다.")
PersonPrediction.objects.create(job=job, track_id=1, action_label="drink_return", confidence=0.2233,
                                second_label="leg_raise_lower", second_confidence=0.1867,
                                margin=0.0367, uncertain=True, frames_seen=24, mean_keypoint_conf=0.623)
PersonPrediction.objects.create(job=job, track_id=2, action_label="drink_return", confidence=0.2367,
                                second_label="leg_raise_lower", second_confidence=0.2067,
                                margin=0.03, uncertain=True, frames_seen=33, mean_keypoint_conf=0.651)
print("작업:", job)
print("이 작업의 예측 수:", job.predictions.count())
for p in job.predictions.all():
    print("  ", p)
print("사용자의 전체 작업 수:", user.analysis_jobs.count())
