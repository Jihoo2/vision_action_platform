"""6·7단계 테스트 (FastAPI·Redis 없이 Mock으로 검증):  python manage.py test analyses"""
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from .models import AnalysisJob
from .services import AIInputError, AIServiceError
from .tasks import run_analysis

User = get_user_model()
TMP_MEDIA = tempfile.mkdtemp()
FAKE_RESULT = {
    "ok": True, "message": "", "processing_time_sec": 0.47,
    "video": {"frames": 33, "fps": 15.28, "duration_sec": 2.16},
    "predictions": [
        {"track_id": 1, "action_label": "drink_return", "confidence": 0.2233, "second_label": "leg_raise_lower",
         "second_confidence": 0.1867, "margin": 0.0367, "uncertain": True, "frames_seen": 24,
         "valid_feature_ratio": 1.0, "mean_keypoint_conf": 0.623, "window_count": 1, "probabilities": {}},
        {"track_id": 2, "action_label": "drink_return", "confidence": 0.2367, "second_label": "leg_raise_lower",
         "second_confidence": 0.2067, "margin": 0.03, "uncertain": True, "frames_seen": 33,
         "valid_feature_ratio": 1.0, "mean_keypoint_conf": 0.651, "window_count": 1},
    ],
}


def make_job(user):
    return AnalysisJob.objects.create(
        user=user, input_type="UPLOAD",
        video=SimpleUploadedFile("clip.mp4", b"fake", content_type="video/mp4"))


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class RunAnalysisTaskTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("member_a", password="pw-A-2026!")

    @mock.patch("analyses.tasks.predict_video", return_value=FAKE_RESULT)
    def test_success_saves_predictions(self, _):
        job = make_job(self.user)
        run_analysis(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "COMPLETED")
        self.assertEqual(job.predictions.count(), 2)          # 작업 1건 = 사람별 결과 2건
        self.assertEqual(job.video_duration_sec, 2.16)
        self.assertIsNotNone(job.finished_at)

    @mock.patch("analyses.tasks.predict_video", side_effect=AIServiceError("AI 서버에 연결할 수 없습니다"))
    def test_ai_server_down_marks_failed(self, _):
        job = make_job(self.user)
        run_analysis(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")
        self.assertIn("연결할 수 없습니다", job.error_message)

    @mock.patch("analyses.tasks.predict_video", side_effect=AIInputError("영상을 열 수 없습니다."))
    def test_bad_video_marks_failed(self, _):
        job = make_job(self.user)
        run_analysis(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")

    @mock.patch("analyses.tasks.predict_video", return_value=FAKE_RESULT)
    def test_not_pending_is_skipped(self, predict):
        job = make_job(self.user)
        AnalysisJob.objects.filter(pk=job.pk).update(status="COMPLETED")
        run_analysis(job.pk)
        predict.assert_not_called()


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class EnqueueTests(APITestCase):
    def test_create_enqueues_after_commit(self):
        user = User.objects.create_user("member_a", password="pw-A-2026!")
        self.client.force_authenticate(user)
        with mock.patch("analyses.views.run_analysis.delay", return_value=mock.Mock(id="task-123")) as delay, \
                self.captureOnCommitCallbacks(execute=True):
            res = self.client.post("/api/v1/analyses/", {
                "input_type": "UPLOAD",
                "video": SimpleUploadedFile("clip.mp4", b"fake", content_type="video/mp4")},
                format="multipart")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "PENDING")        # 응답은 기다리지 않고 즉시 (T05)
        delay.assert_called_once_with(res.data["id"])

    def test_redis_down_marks_failed(self):
        user = User.objects.create_user("member_a", password="pw-A-2026!")
        self.client.force_authenticate(user)
        with mock.patch("analyses.views.run_analysis.delay", side_effect=ConnectionError("redis")), \
                self.captureOnCommitCallbacks(execute=True):
            res = self.client.post("/api/v1/analyses/", {
                "input_type": "UPLOAD",
                "video": SimpleUploadedFile("clip.mp4", b"fake", content_type="video/mp4")},
                format="multipart")
        self.assertEqual(AnalysisJob.objects.get(pk=res.data["id"]).status, "FAILED")
