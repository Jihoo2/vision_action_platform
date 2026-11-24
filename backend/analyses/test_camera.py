"""8단계 IP Webcam 수집 테스트 (실제 카메라 없이 가짜 VideoCapture 사용)"""
import shutil
import tempfile
from unittest import mock

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from pathlib import Path

import cv2

import shutil as _shutil
import unittest

from .camera_capture import CameraError, _retime, capture_clip, to_h264, video_codec
from .models import AnalysisJob
from .tasks import run_analysis

User = get_user_model()
TMP_MEDIA = tempfile.mkdtemp()
CAM = "http://192.168.0.10:8080/video"


class FakeCapture:
    def __init__(self, frames=None, opened=True):
        self.frames = frames
        self.opened = opened

    def isOpened(self):
        return self.opened

    def get(self, prop):
        return 0.0                                   # MJPEG처럼 FPS를 모르는 경우

    def read(self):
        if self.frames is not None:
            if self.frames <= 0:
                return False, None
            self.frames -= 1
        return True, np.zeros((480, 640, 3), dtype=np.uint8)

    def release(self):
        pass


@override_settings(MEDIA_ROOT=TMP_MEDIA, ALLOWED_CAMERA_URLS=[CAM])
class CameraCaptureTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    # _retime 은 저장된 파일을 다시 VideoCapture 로 읽음 → 여기서는 가짜 카메라가
    # 끝없이 Frame을 주므로 _retime 을 막고, 호출 여부만 확인 (실제 동작은 아래 별도 테스트)
    @mock.patch("analyses.camera_capture.to_h264", return_value=True)
    @mock.patch("analyses.camera_capture._retime")
    @mock.patch("analyses.camera_capture.time.sleep")
    @mock.patch("analyses.camera_capture.cv2.VideoCapture", return_value=FakeCapture())
    def test_capture_writes_mp4(self, mock_cap, mock_sleep, mock_retime, mock_h264):
        rel, info = capture_clip(CAM, 1, job_id=1)
        self.assertTrue(rel.endswith(".mp4"))
        self.assertGreaterEqual(info["frames"], 30)
        self.assertLessEqual(info["measured_fps"], 120.0)
        mock_retime.assert_called_once()
        self.assertEqual(mock_retime.call_args.kwargs["max_frames"], info["frames"])
        mock_h264.assert_called_once()
        self.assertEqual(info["codec"], "h264")

    @unittest.skipUnless(_shutil.which("ffmpeg") and _shutil.which("ffprobe"), "ffmpeg 없음")
    def test_to_h264_converts_mp4v(self):
        """OpenCV mp4v 영상 → H.264 로 바뀌고 Frame 수는 그대로"""
        path = Path(TMP_MEDIA) / "codec_test.mp4"
        w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (64, 48))
        for i in range(30):
            w.write(np.full((48, 64, 3), i * 8, dtype=np.uint8))
        w.release()
        self.assertEqual(video_codec(path), "mpeg4")

        self.assertTrue(to_h264(path))

        self.assertEqual(video_codec(path), "h264")
        cap = cv2.VideoCapture(str(path))
        self.assertEqual(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), 30)
        cap.release()

    @mock.patch("analyses.camera_capture.shutil.which", return_value=None)
    def test_to_h264_without_ffmpeg_keeps_file(self, _):
        path = Path(TMP_MEDIA) / "keep.mp4"
        path.write_bytes(b"dummy")
        self.assertFalse(to_h264(path))
        self.assertEqual(path.read_bytes(), b"dummy")

    def test_retime_fixes_fps(self):
        """15fps로 잘못 저장된 40 Frame 영상 → 30fps로 다시 기록 (가짜 없이 실제 OpenCV 사용)"""
        path = Path(TMP_MEDIA) / "retime_test.mp4"
        w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 15.0, (64, 48))
        for i in range(40):
            w.write(np.full((48, 64, 3), i * 5, dtype=np.uint8))
        w.release()

        _retime(path, 30.0, max_frames=40)

        cap = cv2.VideoCapture(str(path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        self.assertAlmostEqual(fps, 30.0, delta=0.5)
        self.assertEqual(count, 40)

    def test_not_allowed_url(self):
        with self.assertRaises(CameraError):
            capture_clip("http://evil.example.com/video", 3, job_id=1)

    @mock.patch("analyses.camera_capture.cv2.VideoCapture", return_value=FakeCapture(opened=False))
    def test_camera_unreachable(self, _):
        with self.assertRaisesMessage(CameraError, "연결할 수 없습니다"):
            capture_clip(CAM, 3, job_id=1)

    @mock.patch("analyses.camera_capture.time.sleep")
    @mock.patch("analyses.camera_capture.cv2.VideoCapture", return_value=FakeCapture(frames=5))
    def test_stream_drops(self, *_):
        with self.assertRaisesMessage(CameraError, "끊겼습니다"):
            capture_clip(CAM, 3, job_id=1)

    @mock.patch("analyses.camera_capture.cv2.VideoCapture", return_value=FakeCapture(opened=False))
    def test_task_marks_failed_when_camera_down(self, _):
        user = User.objects.create_user("member_a", password="pw-A-2026!")
        job = AnalysisJob.objects.create(user=user, input_type="IPCAM", camera_url=CAM, capture_seconds=8)
        run_analysis(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")
        self.assertIn("IP Webcam", job.error_message)
