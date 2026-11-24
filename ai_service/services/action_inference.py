"""[흐름] routers/predictions._analyze() → pose_pipeline.extract_tracks() → 여기 predict_video()
       → Track마다 predict_track() → src/realtime_utils.predict_from_window() (30 Step → RF)

Track ID별 시계열 → 30-Step Sequence(1,140) → Random Forest → 사람별 결과

추론 방식: 6일차 학습과 같은 'Clip 전체' 방식
  한 사람의 전체 유효 Frame을 30 Step으로 Resample → Flatten → predict_proba 1회
  (사전 점검: S03 Test 6/6 정답, 7일차 5초 Window 방식은 2/6 — 짧은 영상에서 Window를 못 채움)

'판단 불확실' 기준
  6일차 모델은 Train 6개로 학습되어 처음 보는 사람의 Confidence가 0.2~0.4 수준입니다.
  7일차 기준(0.55)을 그대로 쓰면 모든 결과가 불확실이 되므로,
  1순위와 2순위 확률 차이(margin)가 작으면 불확실로 표시합니다. (S02 wave는 0.22 완전 동점이었음)
"""
from __future__ import annotations

import os

import numpy as np

from src.realtime_utils import TimedFeatureBuffer, predict_from_window

from .model_loader import ModelBundle
from .pose_pipeline import TrackSeries, VideoResult

UNCERTAIN_MARGIN = float(os.getenv("UNCERTAIN_MARGIN", "0.05"))
# 두 기준은 비슷해 보이지만 역할이 다름
#   MIN_SEEN_FRAMES  : Track 이 잡힌 Frame 수 — 잠깐 스친 오검출 거르기 (predict_video 단계)
#   min_valid_frames : 관절 특징을 만든 Frame 수 — 예측이 가능한지 (predict_track 단계, 학습 정보에서 읽음)
MIN_SEEN_FRAMES = int(os.getenv("MIN_TRACK_FRAMES", "10"))   # 환경 변수 이름은 그대로 (호환)
# 관절 신뢰도 평균이 이보다 낮으면 사람이 아니거나(배경·모니터 속 사람 등) 관절이 거의 안 보이는 Track
MIN_KEYPOINT_CONF = float(os.getenv("MIN_KEYPOINT_CONF", "0.35"))


def predict_track(series: TrackSeries, bundle: ModelBundle) -> dict | None:
    valid = [(t, f) for t, f in zip(series.times, series.features) if f is not None]
    min_valid_frames = int(bundle.training_info.get("min_valid_frames", 10))
    if len(valid) < min_valid_frames:
        return None

    span = valid[-1][0] - valid[0][0] + 1.0
    buf = TimedFeatureBuffer(window_seconds=span)
    for t, f in valid:
        buf.append(t, f)

    # 7일차 함수 재사용 — 첫 반환값(0.55 기준 라벨)은 쓰지 않고, 불확실 판단은 아래 margin 하나로 함
    _, raw_label, conf, probs = predict_from_window(
        bundle.rf, buf, bundle.sequence_steps,
        bundle.realtime.get("confidence_threshold", 0.55),
    )
    probs = np.asarray(probs, dtype=float)
    order = np.argsort(-probs, kind="stable")
    second = int(order[1]) if order[0] == int(np.argmax(probs)) else int(order[0])
    margin = float(conf - probs[second])
    classes = bundle.classes
    return {
        "track_id": series.track_id,
        "action_label": raw_label,
        "confidence": round(float(conf), 4),
        "second_label": classes[second],
        "second_confidence": round(float(probs[second]), 4),
        "margin": round(margin, 4),
        "uncertain": margin < UNCERTAIN_MARGIN,
        "probabilities": {c: round(float(p), 4) for c, p in zip(classes, probs)},
        "frames_seen": series.frames_seen,
        "valid_feature_ratio": round(series.valid_count / max(series.frames_seen, 1), 3),
        "mean_keypoint_conf": round(float(np.mean(series.keypoint_conf)), 3) if series.keypoint_conf else None,
        "window_count": 1,
    }


def predict_video(result: VideoResult, bundle: ModelBundle) -> dict:
    predictions, skipped = [], []
    for tid, s in sorted(result.tracks.items()):
        if s.frames_seen < MIN_SEEN_FRAMES:
            skipped.append({"track_id": tid, "frames_seen": s.frames_seen,
                            "reason": f"{MIN_SEEN_FRAMES} Frame 미만으로 잠깐 잡힌 Track (오검출 가능)"})
            continue
        kconf = float(np.mean(s.keypoint_conf)) if s.keypoint_conf else 0.0
        if kconf < MIN_KEYPOINT_CONF:
            skipped.append({"track_id": tid, "frames_seen": s.frames_seen,
                            "mean_keypoint_conf": round(kconf, 3),
                            "reason": f"관절 신뢰도 평균 {kconf:.2f} < {MIN_KEYPOINT_CONF} (입력 품질 낮음)"})
            continue
        p = predict_track(s, bundle)
        if p is None:
            skipped.append({"track_id": tid, "frames_seen": s.frames_seen,
                            "reason": "유효한 관절 Feature가 부족함"})
        else:
            predictions.append(p)

    if not result.tracks:
        message = "영상에서 사람을 찾지 못했습니다."
    elif not predictions:
        message = "사람은 검출됐지만 동작을 판단할 만큼 관절이 충분히 잡히지 않았습니다."
    elif any(p["uncertain"] for p in predictions):
        message = "일부 결과는 1·2순위 차이가 작아 판단이 불확실합니다."
    else:
        message = ""
    return {"predictions": predictions, "skipped_tracks": skipped, "message": message}
