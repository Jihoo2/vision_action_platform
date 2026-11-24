from django.contrib import admin
from django.db.models import Count

from .models import AnalysisJob, PersonPrediction


class PersonPredictionInline(admin.TabularInline):
    model = PersonPrediction
    extra = 0
    fields = ["track_id", "action_label", "confidence", "second_label", "margin",
              "uncertain", "frames_seen", "mean_keypoint_conf"]
    readonly_fields = fields          # AI 결과는 관리자 화면에서도 수정하지 않음
    can_delete = False


@admin.register(AnalysisJob)
class AnalysisJobAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "input_type", "status", "prediction_count",
                    "expected_action", "video_duration_sec", "created_at", "finished_at"]
    list_filter = ["status", "input_type", "created_at"]
    search_fields = ["user__username", "title", "memo"]
    list_select_related = ["user"]
    date_hierarchy = "created_at"
    readonly_fields = ["status", "celery_task_id", "error_message", "result_message",
                       "video_duration_sec", "processing_time_sec",
                       "created_at", "started_at", "finished_at"]
    fieldsets = [
        ("요청", {"fields": ["user", "title", "memo", "input_type", "video",
                            "camera_url", "capture_seconds", "expected_action"]}),
        ("처리 상태", {"fields": ["status", "celery_task_id", "result_message", "error_message"]}),
        ("시간", {"fields": ["video_duration_sec", "processing_time_sec",
                            "created_at", "started_at", "finished_at"],
                 "classes": ["collapse"]}),
    ]
    inlines = [PersonPredictionInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_pred_count=Count("predictions"))

    @admin.display(description="예측 수", ordering="_pred_count")
    def prediction_count(self, obj):
        return obj._pred_count


@admin.register(PersonPrediction)
class PersonPredictionAdmin(admin.ModelAdmin):
    list_display = ["id", "job", "track_id", "action_label", "confidence",
                    "margin", "uncertain", "predicted_at"]
    list_filter = ["action_label", "uncertain", "job__input_type"]
    search_fields = ["job__user__username", "action_label"]
    list_select_related = ["job", "job__user"]
