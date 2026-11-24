"""9·10단계 화면 테스트:  python manage.py test analyses"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import AnalysisJob, PersonPrediction

User = get_user_model()


class PageTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user("member_a", password="pw-A-2026!")
        self.staff = User.objects.create_superuser("boss", password="pw-S-2026!")
        job = AnalysisJob.objects.create(user=self.member, input_type="UPLOAD", status="COMPLETED")
        PersonPrediction.objects.create(job=job, track_id=1, action_label="wave", confidence=0.33)
        PersonPrediction.objects.create(job=job, track_id=2, action_label="wave", confidence=0.30)
        AnalysisJob.objects.create(user=self.member, input_type="IPCAM", status="FAILED")

    def test_home_goes_to_analyses(self):
        self.client.force_login(self.member)
        self.assertRedirects(self.client.get("/"), "/analyses/")

    def test_analyses_page_requires_login(self):
        self.assertEqual(self.client.get("/analyses/").status_code, 302)
        self.client.force_login(self.member)
        res = self.client.get("/analyses/")
        self.assertContains(res, "AI 분석 시작")
        self.assertContains(res, "IP Webcam")

    def test_dashboard_blocked_for_member(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get("/dashboard/").status_code, 403)

    def test_dashboard_counts_from_db(self):
        self.client.force_login(self.staff)
        res = self.client.get("/dashboard/")
        self.assertEqual(res.status_code, 200)
        chart = res.context["chart"]
        wave_idx = chart["actions"]["labels"].index("A006 손 흔들기")
        self.assertEqual(chart["actions"]["values"][wave_idx], 2)              # wave 예측 2건
        self.assertEqual(sum(chart["status"]["values"]), 2)                     # 작업 2건
        self.assertEqual(chart["status"]["values"][chart["status"]["labels"].index("실패")], 1)
