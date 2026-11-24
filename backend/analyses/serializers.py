"""DRF Serializer — 입력 검증과 JSON 표현

- AnalysisJobCreateSerializer : POST 입력 검증 (업로드 영상 / 허용된 IP Webcam)
- AnalysisJobSerializer       : 목록·상세 응답 (사람별 예측 포함, 전부 읽기 전용)
- AnalysisJobUpdateSerializer : PATCH — 제목·메모만 수정 가능 (상태·AI 결과는 수정 불가)
"""
from pathlib import Path

from django.conf import settings
from rest_framework import serializers

from .models import AnalysisJob, Exercise, PersonPrediction, RepJudgment


class PersonPredictionSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_label_display", read_only=True)

    class Meta:
        model = PersonPrediction
        fields = ["track_id", "action_label", "action_display", "confidence",
                  "second_label", "second_confidence", "margin", "uncertain",
                  "frames_seen", "window_count", "valid_feature_ratio",
                  "mean_keypoint_conf", "extra", "predicted_at"]
        read_only_fields = fields


class RepJudgmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepJudgment
        fields = ["seq", "rep_label", "kind", "verdict", "start_sec", "end_sec", "message",
                  "out_of_range", "boundary", "model_flag", "model_score", "extra"]
        read_only_fields = fields


class AnalysisJobSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="user.username", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    input_type_display = serializers.CharField(source="get_input_type_display", read_only=True)
    predictions = PersonPredictionSerializer(many=True, read_only=True)
    prediction_count = serializers.IntegerField(source="predictions.count", read_only=True)
    task_type_display = serializers.CharField(source="get_task_type_display", read_only=True)
    exercise_display = serializers.CharField(source="get_exercise_display", read_only=True)
    camera_view_display = serializers.CharField(source="get_camera_view_display", read_only=True)
    reps = RepJudgmentSerializer(many=True, read_only=True)

    class Meta:
        model = AnalysisJob
        fields = ["id", "user", "title", "memo",
                  "task_type", "task_type_display", "exercise", "exercise_display",
                  "camera_view", "camera_view_display",
                  "input_type", "input_type_display", "video", "camera_url",
                  "capture_seconds", "expected_action",
                  "status", "status_display", "result_message", "error_message",
                  "model_name", "extra",
                  "video_duration_sec", "processing_time_sec",
                  "created_at", "started_at", "finished_at",
                  "prediction_count", "predictions", "reps"]
        read_only_fields = fields


class AnalysisJobCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisJob
        fields = ["id", "title", "memo", "task_type", "exercise", "camera_view", "input_type", "video",
                  "camera_url", "capture_seconds", "expected_action", "status"]
        read_only_fields = ["id", "status"]
        extra_kwargs = {"video": {"required": False}, "camera_url": {"required": False}}

    def validate_video(self, f):
        if f is None:
            return f
        ext = Path(f.name).suffix.lower()
        if ext not in settings.ALLOWED_VIDEO_EXTENSIONS:
            raise serializers.ValidationError(
                f"지원하지 않는 형식입니다({ext or '확장자 없음'}). 허용: {', '.join(settings.ALLOWED_VIDEO_EXTENSIONS)}")
        if f.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise serializers.ValidationError(f"파일이 너무 큽니다. 최대 {settings.MAX_UPLOAD_MB}MB")
        return f

    def validate(self, attrs):
        task = attrs.get("task_type") or AnalysisJob.TaskType.ACTION
        attrs["task_type"] = task
        if task == AnalysisJob.TaskType.FORM:      # 팀 자세 판정: 판정할 동작이 꼭 필요
            if attrs.get("exercise") not in Exercise.values:
                raise serializers.ValidationError({"exercise": "자세 판정할 동작(버피·런지·스쿼트 점프)을 선택하세요."})
            attrs["expected_action"] = ""
        else:
            attrs["exercise"] = ""
            attrs["camera_view"] = AnalysisJob.CameraView.AUTO
        max_sec = settings.FORM_CAPTURE_MAX_SECONDS if task == AnalysisJob.TaskType.FORM else 15
        kind = attrs.get("input_type")
        if kind == AnalysisJob.InputType.UPLOAD:
            if not attrs.get("video"):
                raise serializers.ValidationError({"video": "영상 업로드 방식은 영상 파일이 필요합니다."})
            attrs["camera_url"] = ""
            attrs["capture_seconds"] = None
        elif kind == AnalysisJob.InputType.IPCAM:
            if attrs.get("video"):
                raise serializers.ValidationError({"video": "IP Webcam 방식에서는 파일을 올리지 않습니다."})
            allowed = settings.ALLOWED_CAMERA_URLS
            url = (attrs.get("camera_url") or "").strip() or (allowed[0] if len(allowed) == 1 else "")
            if url not in allowed:   # 임의의 외부 URL을 서버가 호출하지 않도록 허용 목록만 통과
                raise serializers.ValidationError({"camera_url": "허용되지 않은 카메라 주소입니다."})
            attrs["camera_url"] = url
            sec = attrs.get("capture_seconds") or settings.CAMERA_CAPTURE_SECONDS
            if not 3 <= sec <= max_sec:    # 자세 판정은 여러 회차를 봐야 해서 더 길게 허용
                raise serializers.ValidationError({"capture_seconds": f"수집 시간은 3~{max_sec}초입니다."})
            attrs["capture_seconds"] = sec
        return attrs


class AnalysisJobUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisJob
        fields = ["title", "memo"]          # 이 두 필드 외에는 요청에 있어도 무시됨
