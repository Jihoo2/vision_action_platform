"""5단계 DRF 테스트:  python manage.py test analyses"""
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import AnalysisJob, PersonPrediction

User = get_user_model()
TMP_MEDIA = tempfile.mkdtemp()
CAM = "http://192.168.0.10:8080/video"


def fake_video(name="clip.mp4"):
    return SimpleUploadedFile(name, b"\x00\x00\x00\x18ftypmp42", content_type="video/mp4")


@override_settings(MEDIA_ROOT=TMP_MEDIA, ALLOWED_CAMERA_URLS=[CAM], CAMERA_CAPTURE_SECONDS=8)
class AnalysisApiTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.a = User.objects.create_user("member_a", password="pw-A-2026!")
        self.b = User.objects.create_user("member_b", password="pw-B-2026!")
        self.staff = User.objects.create_superuser("boss", password="pw-S-2026!")
        self.job_b = AnalysisJob.objects.create(user=self.b, input_type="UPLOAD", title="B의 작업")
        PersonPrediction.objects.create(job=self.job_b, track_id=1, action_label="wave", confidence=0.33)

    # ---------- 인증 ----------
    def test_anonymous_rejected(self):
        self.assertEqual(self.client.get("/api/v1/analyses/").status_code, 403)

    # ---------- Create ----------
    def test_create_upload_job_is_pending(self):
        self.client.force_authenticate(self.a)
        res = self.client.post("/api/v1/analyses/",
                               {"input_type": "UPLOAD", "video": fake_video(), "expected_action": "wave"},
                               format="multipart")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["status"], "PENDING")
        self.assertEqual(AnalysisJob.objects.get(pk=res.data["id"]).user, self.a)

    def test_upload_without_file_rejected(self):
        self.client.force_authenticate(self.a)
        res = self.client.post("/api/v1/analyses/", {"input_type": "UPLOAD"}, format="multipart")
        self.assertEqual(res.status_code, 400)

    def test_wrong_extension_rejected(self):
        self.client.force_authenticate(self.a)
        res = self.client.post("/api/v1/analyses/",
                               {"input_type": "UPLOAD", "video": fake_video("bad.txt")}, format="multipart")
        self.assertEqual(res.status_code, 400)

    def test_ipcam_allowed_url_and_default_seconds(self):
        self.client.force_authenticate(self.a)
        res = self.client.post("/api/v1/analyses/", {"input_type": "IPCAM"}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["camera_url"], CAM)
        self.assertEqual(res.data["capture_seconds"], 8)

    def test_ipcam_unknown_url_rejected(self):
        self.client.force_authenticate(self.a)
        res = self.client.post("/api/v1/analyses/",
                               {"input_type": "IPCAM", "camera_url": "http://evil.example.com/x"}, format="json")
        self.assertEqual(res.status_code, 400)

    # ---------- Read · T07 ----------
    def test_list_shows_only_my_jobs(self):
        AnalysisJob.objects.create(user=self.a, input_type="UPLOAD", title="A의 작업")
        self.client.force_authenticate(self.a)
        titles = [j["title"] for j in self.client.get("/api/v1/analyses/").data["results"]]
        self.assertEqual(titles, ["A의 작업"])

    def test_cannot_read_update_delete_others_job(self):
        self.client.force_authenticate(self.a)
        url = f"/api/v1/analyses/{self.job_b.id}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(url + "status/").status_code, 404)
        self.assertEqual(self.client.patch(url, {"title": "해킹"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.job_b.refresh_from_db()
        self.assertEqual(self.job_b.title, "B의 작업")

    def test_staff_sees_all(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/v1/analyses/").data["count"], 1)
        self.assertEqual(self.client.get(f"/api/v1/analyses/{self.job_b.id}/").status_code, 200)

    # ---------- Update ----------
    def test_patch_only_title_memo(self):
        self.client.force_authenticate(self.b)
        res = self.client.patch(f"/api/v1/analyses/{self.job_b.id}/",
                                {"title": "새 제목", "status": "COMPLETED"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.job_b.refresh_from_db()
        self.assertEqual(self.job_b.title, "새 제목")
        self.assertEqual(self.job_b.status, "PENDING")          # 상태는 바뀌지 않음

    def test_put_not_allowed(self):
        self.client.force_authenticate(self.b)
        res = self.client.put(f"/api/v1/analyses/{self.job_b.id}/", {"title": "x"}, format="json")
        self.assertEqual(res.status_code, 405)

    # ---------- Delete ----------
    def test_delete_cascades_predictions(self):
        self.client.force_authenticate(self.b)
        self.assertEqual(self.client.delete(f"/api/v1/analyses/{self.job_b.id}/").status_code, 204)
        self.assertFalse(PersonPrediction.objects.exists())

    def test_status_endpoint(self):
        self.client.force_authenticate(self.b)
        res = self.client.get(f"/api/v1/analyses/{self.job_b.id}/status/")
        self.assertEqual(res.data["status"], "PENDING")
        self.assertFalse(res.data["done"])
