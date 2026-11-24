"""6일차 학습 산출물과 YOLO Pose 모델을 서버 시작 시 1회 로드하고 규격을 검사합니다.

- rf_action_baseline.joblib  : 6개 Action Random Forest (입력 1,140)
- rf_feature_columns.json    : 학습 때 Feature 이름·순서 (t00_nose_x ... t29_right_knee_angle)
- rf_training_info.json      : sequence_steps(30), classes, min_valid_frames
- yolo11n-pose.pt            : 학습 때 사용한 Pose 모델 (project.json)
- configs/day07_realtime.json, day08_multi_person.json : 신뢰도 기준·Tracker 설정
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib

BASE_DIR = Path(__file__).resolve().parents[1]          # ai_service/
MODEL_DIR = BASE_DIR / "models"
CONFIG_DIR = BASE_DIR / "configs"
FRAME_FEATURE_DIM = 38


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_device(requested: str) -> str:
    if requested and requested != "auto":
        return requested
    try:
        import torch
        return "cuda:0" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001
        return "cpu"


@dataclass
class ModelBundle:
    rf: object
    feature_columns: list
    training_info: dict
    project: dict
    realtime: dict
    multi_person: dict
    pose: object
    device: str
    checks: dict = field(default_factory=dict)

    @property
    def classes(self) -> list[str]:
        return [str(c) for c in self.rf.classes_]

    @property
    def sequence_steps(self) -> int:
        return int(self.training_info["sequence_steps"])

    @property
    def ready(self) -> bool:
        return all(self.checks.values())


_bundle: ModelBundle | None = None


def load_models() -> ModelBundle:
    """서버 시작 시 1회 호출. 이후 요청은 get_bundle()로 같은 객체를 재사용합니다."""
    global _bundle
    if _bundle is not None:
        return _bundle

    from ultralytics import YOLO

    rf = joblib.load(MODEL_DIR / "rf_action_baseline.joblib")
    cols = _read_json(MODEL_DIR / "rf_feature_columns.json")
    if isinstance(cols, dict):
        cols = next(v for v in cols.values() if isinstance(v, list))
    info = _read_json(MODEL_DIR / "rf_training_info.json")
    project = _read_json(BASE_DIR / "project.json")
    realtime = _read_json(CONFIG_DIR / "day07_realtime.json")
    multi = _read_json(CONFIG_DIR / "day08_multi_person.json")

    pose_path = MODEL_DIR / Path(project["pose_model"]).name
    device = _resolve_device(project.get("device", "auto"))
    pose = YOLO(str(pose_path))

    steps = int(info["sequence_steps"])
    checks = {
        "n_features_in_==1140": int(rf.n_features_in_) == 1140,
        "steps*38==n_features_in_": steps * FRAME_FEATURE_DIM == int(rf.n_features_in_),
        "feature_columns==n_features_in_": len(cols) == int(rf.n_features_in_),
        "classes==6": len(rf.classes_) == 6,
        "classes==training_info": [str(c) for c in rf.classes_] == list(info["classes"]),
    }
    _bundle = ModelBundle(rf, cols, info, project, realtime, multi, pose, device, checks)
    if not _bundle.ready:
        failed = [k for k, v in checks.items() if not v]
        raise RuntimeError(f"모델 규격 검사 실패: {failed}")
    return _bundle


def get_bundle() -> ModelBundle | None:
    return _bundle
