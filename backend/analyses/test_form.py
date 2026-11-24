"""팀 자세 판정(FORM) 연결 테스트 — form_service 없이 Mock으로 검증:  python manage.py test analyses"""
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from .models import AnalysisJob, RepJudgment
from .services import AIServiceError, judge_form
from .tasks import run_analysis

User = get_user_model()
TMP_MEDIA = tempfile.mkdtemp()
CAM = "http://192.168.0.10:8080/video"

FAKE_FORM = {
    "ok": True, "model": {"name": "team05_form_rules", "action": "A004"},
    "message": "런지 2회: OK 1 · NG 1 · CHECK 0 (얕은 시도 1)", "processing_time_sec": 12.3,
    "meta": {"action": "A004", "view": "side", "view_requested": "auto", "fps": 30.0,
             "frames": 300, "duration_sec": 10.0, "standards_loaded": True},
    "summary": {"reps": 2, "ok": 1, "ng": 2, "check": 0, "shallow": 1, "attention": 1},
    "reps": [
        {"kind": "rep", "rep": 1, "verdict": "OK", "message": "좋습니다", "start_s": 1.2, "end_s": 2.9,
         "view": "side", "checks": [{"metric": "knee_min", "value": 92.1, "lo": 60, "hi": 115, "ok": True}],
         "values": {"knee_min": 92.1}, "model_score": 0.8, "model_flag": ""},
        {"kind": "rep", "rep": 2, "verdict": "NG", "message": "더 깊이 앉으세요", "out_of_range": "depth>0.55",
         "boundary": "", "start_s": 4.0, "end_s": 5.5, "model_score": 2.7, "model_flag": "주의",
         "checks": [{"metric": "depth", "value": 0.63, "lo": None, "hi": 0.55, "ok": False}]},
        {"kind": "shallow", "rep": "얕은1", "verdict": "NG", "message": "더 깊이 내려가세요",
         "out_of_range": "depth>shallow_attempt", "start_s": 7.0, "end_s": 7.8},
    ],
}


def fake_video(name="lunge.mp4"):
    return SimpleUploadedFile(name, b"\x00\x00\x00\x18ftypmp42", content_type="video/mp4")


@override_settings(MEDIA_ROOT=TMP_MEDIA, ALLOWED_CAMERA_URLS=[CAM], FORM_CAPTURE_MAX_SECONDS=30)
class FormApiTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.a = User.objects.create_user("member_a", password="pw-A-2026!")
        self.client.force_authenticate(self.a)

    def post(self, data, fmt="multipart"):
        return self.client.post("/api/v1/analyses/", data, format=fmt)

    def test_form_requires_exercise(self):
        res = self.post({"task_type": "FORM", "input_type": "UPLOAD", "video": fake_video()})
        self.assertEqual(res.status_code, 400)
        self.assertIn("exercise", res.data)

    def test_form_upload_created(self):
        res = self.post({"task_type": "FORM", "exercise": "A004", "camera_view": "side",
                         "input_type": "UPLOAD", "video": fake_video(), "expected_action": "wave"})
        self.assertEqual(res.status_code, 201, res.data)
        job = AnalysisJob.objects.get(pk=res.data["id"])
        self.assertEqual((job.task_type, job.exercise, job.camera_view), ("FORM", "A004", "side"))
        self.assertEqual(job.expected_action, "")            # 6개 동작용 값은 자세 판정에서 비움
        self.assertEqual(res.data["reps"], [])

    def test_action_job_ignores_form_fields(self):
        res = self.post({"input_type": "UPLOAD", "video": fake_video(), "exercise": "A004", "camera_view": "side"})
        self.assertEqual(res.status_code, 201, res.data)
        job = AnalysisJob.objects.get(pk=res.data["id"])
        self.assertEqual((job.task_type, job.exercise, job.camera_view), ("ACTION", "", "auto"))

    def test_unknown_exercise_rejected(self):
        res = self.post({"task_type": "FORM", "exercise": "A006", "input_type": "UPLOAD", "video": fake_video()})
        self.assertEqual(res.status_code, 400)

    def test_status_api_counts_only_its_type(self):
        """상태 API: 자세 판정 작업은 회차 수만, 예측 수는 0 (COUNT 쿼리 1번)"""
        res = self.post({"task_type": "FORM", "exercise": "A004", "input_type": "UPLOAD", "video": fake_video()})
        job = AnalysisJob.objects.get(pk=res.data["id"])
        RepJudgment.objects.create(job=job, seq=1, rep_label="1", verdict="OK")
        st = self.client.get(f"/api/v1/analyses/{job.id}/status/").data
        self.assertEqual((st["rep_count"], st["prediction_count"]), (1, 0))

    def test_ipcam_form_allows_longer_capture(self):
        ok = self.post({"task_type": "FORM", "exercise": "A008", "input_type": "IPCAM", "capture_seconds": 25}, "json")
        self.assertEqual(ok.status_code, 201, ok.data)
        too_long = self.post({"input_type": "IPCAM", "capture_seconds": 25}, "json")     # 동작 인식은 15초까지
        self.assertEqual(too_long.status_code, 400)


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class FormTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("member_a", password="pw-A-2026!")
        self.job = AnalysisJob.objects.create(user=self.user, input_type="UPLOAD", task_type="FORM",
                                              exercise="A004", camera_view="auto", video=fake_video())

    @mock.patch("analyses.tasks.predict_video")
    @mock.patch("analyses.tasks.judge_form", return_value=FAKE_FORM)
    def test_form_saves_reps(self, m_form, m_action):
        run_analysis(self.job.pk)
        self.job.refresh_from_db()
        m_form.assert_called_once()
        self.assertEqual(m_form.call_args.args[1:], ("A004", "auto"))
        m_action.assert_not_called()                         # 6개 동작 서버는 호출하지 않음
        self.assertEqual(self.job.status, "COMPLETED")
        self.assertEqual(self.job.model_name, "team05_form_rules")
        self.assertEqual(self.job.video_duration_sec, 10.0)
        self.assertEqual(self.job.extra["summary"]["ng"], 2)
        self.assertEqual(self.job.extra["schema"], "form.v1")
        reps = list(self.job.reps.all())
        self.assertEqual([r.verdict for r in reps], ["OK", "NG", "NG"])
        self.assertEqual(reps[2].rep_label, "얕은1")
        self.assertEqual(reps[2].kind, "shallow")
        self.assertTrue(reps[1].model_flag)
        self.assertEqual(reps[1].extra["checks"][0]["metric"], "depth")
        self.assertEqual(self.job.predictions.count(), 0)

    @mock.patch("analyses.tasks.judge_form", return_value=FAKE_FORM)
    def test_rerun_does_not_duplicate(self, _):
        run_analysis(self.job.pk)
        AnalysisJob.objects.filter(pk=self.job.pk).update(status="PENDING")
        run_analysis(self.job.pk)
        self.assertEqual(RepJudgment.objects.filter(job=self.job).count(), 3)

    @mock.patch("analyses.tasks.judge_form", side_effect=AIServiceError("자세 판정 AI 서버에 연결할 수 없습니다"))
    def test_form_server_down_marks_failed(self, _):
        run_analysis(self.job.pk)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "FAILED")
        self.assertIn("자세 판정", self.job.error_message)

    @override_settings(FORM_SERVICE_URL="http://formjudge:8002")
    @mock.patch("analyses.services.httpx.post")
    def test_judge_form_sends_action_and_view(self, m_post):
        m_post.return_value = mock.Mock(status_code=200, json=lambda: FAKE_FORM)
        out = judge_form(self.job.video.path, "A004", "side")
        self.assertEqual(out["summary"]["reps"], 2)
        url = m_post.call_args.args[0]
        self.assertEqual(url, "http://formjudge:8002/api/v1/judge/")
        self.assertEqual(m_post.call_args.kwargs["data"], {"action": "A004", "view": "side"})


class FormDashboardTests(TestCase):
    def test_dashboard_has_form_chart(self):
        boss = User.objects.create_superuser("boss", password="pw-S-2026!")
        job = AnalysisJob.objects.create(user=boss, input_type="UPLOAD", task_type="FORM", exercise="A004")
        RepJudgment.objects.create(job=job, seq=1, rep_label="1", verdict="NG")
        self.client.force_login(boss)
        res = self.client.get("/dashboard/")
        self.assertEqual(res.status_code, 200)
        form = res.context["chart"]["form"]
        ng = next(d for d in form["datasets"] if d["label"] == "NG")
        self.assertEqual(ng["values"][form["labels"].index("런지")], 1)
