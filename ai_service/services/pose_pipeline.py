"""영상 1개 → YOLO Pose + ByteTrack → Track ID별 (시간, 38-D Feature) 시계열

7~8일차 수업 코드를 그대로 사용합니다.
  - Tracking : model.track(..., tracker=bytetrack.yaml)       (8일차 47·49번)
  - Feature  : src.multi_person_utils.feature_from_keypoints  (3일차 정규화 + 각도, 38-D)
한 사람이 여러 명이어도 Track ID마다 따로 모읍니다.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

import cv2
import numpy as np

from src.multi_person_utils import feature_from_keypoints

from .model_loader import ModelBundle

# YOLO 추적기 상태는 모델 객체 안에 저장되므로, 동시에 두 영상을 처리하면 섞입니다.
_track_lock = threading.Lock()


class VideoReadError(Exception):
    """영상 파일을 열 수 없거나 Frame이 없을 때 (손상·형식 오류)"""


@dataclass
class TrackSeries:
    track_id: int
    times: list = field(default_factory=list)
    features: list = field(default_factory=list)       # np.ndarray(38,) 또는 None
    keypoint_conf: list = field(default_factory=list)
    box_conf: list = field(default_factory=list)

    @property
    def frames_seen(self) -> int:
        return len(self.times)

    @property
    def valid_count(self) -> int:
        return sum(f is not None for f in self.features)


@dataclass
class VideoResult:
    frames: int
    fps: float
    width: int
    height: int
    tracks: dict[int, TrackSeries]

    @property
    def duration_sec(self) -> float:
        return self.frames / self.fps if self.fps > 0 else 0.0


def extract_tracks(video_path: str, bundle: ModelBundle, max_seconds: float | None = None) -> VideoResult:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise VideoReadError("영상을 열 수 없습니다. 손상되었거나 지원하지 않는 형식입니다.")
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 0.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0:
        cap.release()
        raise VideoReadError("영상 FPS를 확인할 수 없습니다.")

    cfg = bundle.project
    tracks: dict[int, TrackSeries] = {}
    frame_id = 0
    with _track_lock:
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                now = frame_id / fps
                if max_seconds and now > max_seconds:
                    break
                # 첫 Frame은 persist=False 로 추적기를 새로 만들어 이전 영상의 ID가 이어지지 않게 함
                res = bundle.pose.track(
                    source=frame, persist=frame_id > 0,
                    tracker=bundle.multi_person.get("tracker", "bytetrack.yaml"),
                    imgsz=int(cfg.get("image_size", 640)),
                    conf=float(cfg.get("person_confidence", 0.25)),
                    device=bundle.device, verbose=False,
                )[0]
                boxes, kps = res.boxes, res.keypoints
                if boxes is not None and len(boxes) and boxes.id is not None and kps is not None:
                    ids = boxes.id.detach().cpu().numpy().astype(int)
                    bconf = boxes.conf.detach().cpu().numpy()
                    xy = kps.xy.detach().cpu().numpy()
                    kconf = kps.conf.detach().cpu().numpy() if kps.conf is not None else None
                    for i in range(min(len(ids), len(xy))):
                        tid = int(ids[i])
                        s = tracks.setdefault(tid, TrackSeries(tid))
                        s.times.append(now)
                        s.features.append(feature_from_keypoints(xy[i]))
                        s.box_conf.append(float(bconf[i]))
                        if kconf is not None and i < len(kconf):
                            s.keypoint_conf.append(float(np.mean(kconf[i])))
                frame_id += 1
        finally:
            cap.release()

    if frame_id == 0:
        raise VideoReadError("읽을 수 있는 Frame이 없습니다.")
    return VideoResult(frame_id, fps, width, height, tracks)
