"""팀 프로젝트(G5_skeleton/subject10_team_pilot) 자세 판정 엔진 연결

팀 코드는 복사하지 않고 TEAM_DIR 로 연결합니다 (Docker 에서는 읽기 전용 볼륨).
  - 판정: src.realtime_judge.OnlineJudge — 팀 웹(web/processing.py)·실시간·터미널 판정과 같은 엔진
  - 기준: reports/team_projects/team05/standards/{동작}_{각도}.json  (team_08)
  - 정석 곡선: reports/.../reference/{동작}_{각도}_template.json      (team_07)
  - 이상 탐지: reports/.../models/form_model_{동작}.npz               (team_20, 있으면 '주의' 표시)
Pose 는 이 서비스의 YOLO 가중치(POSE_MODEL)로 Frame마다 가장 점수가 높은 한 명을 씁니다 (팀 웹과 같은 방식).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

TEAM_DIR = Path(os.getenv("TEAM_DIR", "/team")).expanduser().resolve()
POSE_MODEL = os.getenv("POSE_MODEL", "/app/models/yolo11n-pose.pt")
ACTIONS = {"A001": "버피", "A004": "런지", "A008": "스쿼트 점프"}   # 팀이 판정하는 3개 동작 (A006은 보류)
VIEWS = ("auto", "front", "diag", "side")
MODEL_NAME = "team05_form_rules"


class VideoReadError(Exception):
    pass


@dataclass
class TeamEngine:
    cfg: dict = field(default_factory=dict)
    paths: dict = field(default_factory=dict)
    pose_cfg: dict = field(default_factory=dict)
    pose: object = None
    device: object = "cpu"
    OnlineJudge: type | None = None
    error: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)

    # ---------------------------------------------------------------- 시작 시 1회
    def load(self, load_pose: bool = True) -> "TeamEngine":
        try:
            if not (TEAM_DIR / "src" / "realtime_judge.py").exists():
                raise FileNotFoundError(f"팀 프로젝트를 찾을 수 없습니다: {TEAM_DIR} (TEAM_DIR 확인)")
            if str(TEAM_DIR) not in sys.path:
                sys.path.insert(0, str(TEAM_DIR))
            from src.realtime_judge import OnlineJudge          # noqa: E402  팀 판정 엔진
            from src.team_feature_utils import load_team_config, team_paths
            self.OnlineJudge = OnlineJudge
            self.cfg = load_team_config()
            self.paths = team_paths(self.cfg)
            self.pose_cfg = json.loads((TEAM_DIR / "configs" / "project.json").read_text(encoding="utf-8"))
            if load_pose:
                import torch
                from ultralytics import YOLO
                self.pose = YOLO(POSE_MODEL)
                self.device = 0 if torch.cuda.is_available() else "cpu"
        except Exception as e:  # noqa: BLE001  /health 에 원인 표시
            self.error = f"{e.__class__.__name__}: {e}"
        return self

    @property
    def ready(self) -> bool:
        return not self.error and self.OnlineJudge is not None and self.pose is not None

    def artifacts(self) -> dict:
        """동작·각도별 판정 기준 파일이 있는지 (없으면 그 각도는 CHECK 로만 나옴)"""
        if not self.paths:
            return {}
        out = {}
        for aid in ACTIONS:
            out[aid] = {
                "standards": sorted(p.stem.split("_", 1)[1] for p in self.paths["standards"].glob(f"{aid}_*.json")),
                "templates": sorted(p.name.split("_")[1] for p in self.paths["reference"].glob(f"{aid}_*_template.json")),
                "form_model": (self.paths["reports"] / "models" / f"form_model_{aid}.npz").exists(),
            }
        return out

    # ---------------------------------------------------------------- Pose (가장 점수 높은 한 명)
    def predict_pose(self, frame) -> tuple[np.ndarray, np.ndarray]:
        r = self.pose.predict(source=frame, imgsz=self.pose_cfg.get("image_size", 640),
                              conf=self.pose_cfg.get("person_confidence", 0.25),
                              device=self.device, verbose=False)[0]
        xy, conf = np.full((17, 2), np.nan), np.zeros(17)
        if r.boxes is not None and len(r.boxes) and r.keypoints is not None and r.keypoints.conf is not None:
            i = int(np.argmax(r.boxes.conf.cpu().numpy()))
            xy, conf = r.keypoints.xy.cpu().numpy()[i], r.keypoints.conf.cpu().numpy()[i]
        return xy, conf

    # ---------------------------------------------------------------- 영상 1개 판정
    def judge_video(self, path: str, action: str, view: str = "auto", max_seconds: float = 120.0) -> dict:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise VideoReadError("영상을 열 수 없습니다. 손상되었거나 지원하지 않는 형식입니다.")
        fps = cap.get(cv2.CAP_PROP_FPS)
        fps = fps if fps and 5 < fps < 121 else 30.0
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        judge = self.OnlineJudge(self.cfg, action, view, self.paths, fps, "team", use_model=True)
        events, n, seen, t0 = [], 0, 0, time.time()
        with self.lock:                                       # YOLO 는 한 번에 하나씩
            while n < int(max_seconds * fps):
                ok, frame = cap.read()
                if not ok:
                    break
                n += 1
                xy, conf = self.predict_pose(frame)
                seen += int(np.isfinite(xy).any())
                events += judge.push(n, (n - 1) / fps, xy, conf)
            cap.release()
            events += judge.flush()
        if n == 0:
            raise VideoReadError("영상에서 Frame을 읽지 못했습니다.")
        return finalize(judge, events, action, view, fps, n, seen, w, h, time.time() - t0)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    return o


def finalize(judge, events, action, view, fps, n, seen, w, h, seconds) -> dict:
    """팀 이벤트 → 서비스 응답 (곡선 배열은 화면에서 쓰지 않아 뺌)"""
    reps = [{k: v for k, v in e.items() if k not in ("curve", "template")} for e in events]
    counts = dict(judge.counts)
    summary = dict(reps=judge.rep_no, ok=counts.get("OK", 0), ng=counts.get("NG", 0),
                   check=counts.get("CHECK", 0),
                   shallow=sum(1 for e in events if e.get("kind") == "shallow"),
                   attention=sum(1 for e in events if e.get("model_flag")))
    std_ok = bool(getattr(judge, "metrics", None))
    if not reps:
        msg = ("사람이 검출되지 않았습니다." if seen == 0
               else "판정할 회차를 찾지 못했습니다. 전신이 보이게 서서 동작을 반복해 주세요.")
    else:
        msg = f"{ACTIONS.get(action, action)} {summary['reps']}회: OK {summary['ok']} · NG {summary['ng']} · CHECK {summary['check']}"
        if summary["shallow"]:
            msg += f" (얕은 시도 {summary['shallow']})"
        if not std_ok:
            msg += " — 이 각도의 판정 기준 파일이 없어 CHECK 로 표시"
    return _clean(dict(
        meta=dict(action=action, action_ko=ACTIONS.get(action, action), view=judge.view or view,
                  view_requested=view, fps=round(fps, 2), width=w, height=h, frames=n,
                  person_frames=seen, duration_sec=round(n / fps, 2), standards_loaded=std_ok),
        summary=summary, reps=reps, message=msg, processing_time_sec=round(seconds, 2)))
