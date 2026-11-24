"""IP Webcam에서 정해진 시간만 프레임을 읽어 MP4로 저장 (Celery Worker가 실행)

- 허용 목록(.env ALLOWED_CAMERA_URLS)에 있는 주소만 연결 → 서버가 임의 URL을 호출하지 않음
- 연결 실패·도중 끊김·프레임 부족은 CameraError 로 알림 → 작업 FAILED + 사유 저장 (T09)
- 저장한 MP4는 업로드 영상과 똑같이 FastAPI /api/v1/predict/ 로 보냄 (추론 경로 재사용)

[흐름] tasks._acquire_video() → capture_clip() → (_retime) → to_h264() → 경로 반환
       → tasks.run_analysis() 가 services 로 AI 서버 호출

참고: 추론은 '사람별 전체 Frame → 30 Step Resample' 방식이라 FPS 절댓값보다
      수집 구간 안에서 Frame 순서·간격이 유지되는 것이 중요합니다.
"""
import logging
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import cv2
from django.conf import settings

OPEN_TIMEOUT_MS = 5000          # 카메라 연결 대기
READ_FAIL_LIMIT = 30            # 연속 읽기 실패 허용 횟수 (끊김 판단)
MIN_FRAMES = 30                 # 이보다 적으면 동작을 판단할 수 없음
MAX_WIDTH = 960                 # 큰 해상도는 줄여서 저장 (Pose 입력은 640)


logger = logging.getLogger(__name__)


class CameraError(Exception):
    pass


def capture_clip(camera_url: str, seconds: int, job_id: int) -> tuple[str, dict]:
    """카메라에서 seconds 초 동안 수집 → (media 기준 상대경로, 수집 정보)"""
    if camera_url not in settings.ALLOWED_CAMERA_URLS:
        raise CameraError("허용되지 않은 카메라 주소입니다.")

    cap = cv2.VideoCapture(camera_url, cv2.CAP_FFMPEG,
                           [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS,
                            cv2.CAP_PROP_READ_TIMEOUT_MSEC, OPEN_TIMEOUT_MS])
    if not cap.isOpened():
        raise CameraError("IP Webcam에 연결할 수 없습니다. 휴대폰 앱의 서버 실행·같은 Wi-Fi·주소를 확인하세요.")

    rel = Path("captures") / datetime.now().strftime("%Y/%m/%d") / f"job{job_id}_{datetime.now():%H%M%S}.mp4"
    out_path = Path(settings.MEDIA_ROOT) / rel
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # stream_fps : 카메라가 알려 준 값 그대로 (MJPEG 스트림은 0 을 주는 경우가 많음)
    # write_fps  : 파일을 처음 쓸 때 쓰는 값 — 알려 주지 않으면 임시로 15
    stream_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    write_fps = stream_fps if 1 <= stream_fps <= 60 else 15.0
    writer = None
    frames, fails = 0, 0
    started = time.monotonic()
    try:
        while time.monotonic() - started < seconds:
            ok, frame = cap.read()
            if not ok or frame is None:
                fails += 1
                if fails >= READ_FAIL_LIMIT:
                    raise CameraError(f"카메라 영상이 끊겼습니다. ({frames} Frame 수집 후 중단)")
                time.sleep(0.05)
                continue
            fails = 0
            h, w = frame.shape[:2]
            if w > MAX_WIDTH:
                frame = cv2.resize(frame, (MAX_WIDTH, int(h * MAX_WIDTH / w)))
            if writer is None:
                h, w = frame.shape[:2]
                writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), write_fps, (w, h))
                if not writer.isOpened():
                    raise CameraError("수집 영상을 저장할 수 없습니다.")
            writer.write(frame)
            frames += 1
    finally:
        cap.release()
        if writer is not None:
            writer.release()

    elapsed = time.monotonic() - started
    if frames < MIN_FRAMES:
        out_path.unlink(missing_ok=True)
        raise CameraError(f"수집된 Frame이 너무 적습니다 ({frames}개 / {elapsed:.1f}초).")

    # 처음 쓴 FPS(write_fps)와 실제 수신 속도(measured_fps)가 다르면 영상 길이가 틀어짐
    # (예: 8초 수집인데 19초짜리 파일) → 실제 측정 FPS로 다시 기록
    measured_fps = frames / elapsed if elapsed else write_fps
    measured_fps = min(max(measured_fps, 1.0), 120.0)   # 비정상 값 방지
    if abs(measured_fps - write_fps) > 1.0:
        _retime(out_path, measured_fps, max_frames=frames)
    codec = "h264" if to_h264(out_path) else "mp4v"
    return str(rel), {"frames": frames, "seconds": round(elapsed, 2),
                      "measured_fps": round(measured_fps, 2), "stream_fps": stream_fps,
                      "write_fps": write_fps,
                      "codec": codec}


def _retime(path: Path, fps: float, max_frames: int) -> None:
    """같은 Frame을 올바른 FPS로 다시 써서 영상 길이를 실제 수집 시간과 맞춤

    max_frames: 방금 저장한 Frame 수. 이만큼만 다시 읽어 무한 루프를 막음
    """
    tmp = path.with_suffix(".retime.mp4")
    src = cv2.VideoCapture(str(path))
    w = int(src.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(src.get(cv2.CAP_PROP_FRAME_HEIGHT))
    dst = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    try:
        for _ in range(max_frames):
            ok, frame = src.read()
            if not ok:
                break
            dst.write(frame)
    finally:
        src.release()
        dst.release()
    tmp.replace(path)


def video_codec(path: Path) -> str | None:
    """ffprobe 로 첫 영상 스트림의 코덱 이름 확인 (h264, mpeg4 ...)"""
    if not shutil.which("ffprobe"):
        return None
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    return out.stdout.strip() or None


def to_h264(path: Path) -> bool:
    """OpenCV 가 쓴 mp4v(MPEG-4 Part 2) 영상을 브라우저가 재생하는 H.264 로 변환

    - Chrome/Edge 의 <video> 는 mp4v 를 재생하지 못함 (0:00 에서 멈춤)
    - pip 의 opencv-python-headless 에는 H.264 인코더가 없어서 ffmpeg 로 변환
    - +faststart: 파일 앞쪽에 색인을 두어 내려받는 중에도 바로 재생
    - ffmpeg 가 없거나 실패하면 원본(mp4v)을 그대로 둠 → 분석에는 영향 없음
    """
    if not shutil.which("ffmpeg"):
        logger.warning("ffmpeg 가 없어 H.264 변환을 건너뜀: %s", path)
        return False
    tmp = path.with_suffix(".h264.mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(tmp)],
            check=True, capture_output=True, timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.warning("H.264 변환 실패 (%s): %s", path, exc)
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(path)
    return True
