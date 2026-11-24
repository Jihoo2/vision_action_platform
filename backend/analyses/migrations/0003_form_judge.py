# 팀 자세 판정(FORM) 연결: 분석 종류·판정 동작·촬영 각도 + 회차별 판정 테이블
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analyses", "0002_analysisjob_extra_analysisjob_model_name_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="analysisjob",
            name="task_type",
            field=models.CharField(choices=[("ACTION", "동작 인식 (6개 동작)"), ("FORM", "자세 판정 (팀 모델)")],
                                   db_index=True, default="ACTION", max_length=10, verbose_name="분석 종류"),
        ),
        migrations.AddField(
            model_name="analysisjob",
            name="exercise",
            field=models.CharField(blank=True, choices=[("A001", "버피"), ("A004", "런지"), ("A008", "스쿼트 점프")],
                                   max_length=10, verbose_name="판정 동작(자세 판정)"),
        ),
        migrations.AddField(
            model_name="analysisjob",
            name="camera_view",
            field=models.CharField(choices=[("auto", "자동 추정"), ("front", "정면"), ("diag", "사선 45°"), ("side", "측면")],
                                   default="auto", max_length=10, verbose_name="촬영 각도(자세 판정)"),
        ),
        migrations.CreateModel(
            name="RepJudgment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seq", models.PositiveIntegerField(verbose_name="순서")),
                ("rep_label", models.CharField(max_length=12, verbose_name="회차")),
                ("kind", models.CharField(default="rep", max_length=10, verbose_name="종류")),
                ("verdict", models.CharField(choices=[("OK", "OK"), ("NG", "NG"), ("CHECK", "CHECK")],
                                             db_index=True, max_length=6, verbose_name="판정")),
                ("start_sec", models.FloatField(blank=True, null=True, verbose_name="시작(초)")),
                ("end_sec", models.FloatField(blank=True, null=True, verbose_name="끝(초)")),
                ("message", models.CharField(blank=True, max_length=255, verbose_name="교정 메시지")),
                ("out_of_range", models.CharField(blank=True, max_length=255, verbose_name="기준을 벗어난 지표")),
                ("boundary", models.CharField(blank=True, max_length=255, verbose_name="경계 지표(±2%)")),
                ("model_flag", models.BooleanField(default=False, verbose_name="이상 탐지 '주의'")),
                ("model_score", models.FloatField(blank=True, null=True, verbose_name="이상 탐지 점수")),
                ("extra", models.JSONField(blank=True, default=dict, verbose_name="측정값·기준")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="판정 시각")),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reps",
                                          to="analyses.analysisjob", verbose_name="분석 작업")),
            ],
            options={
                "verbose_name": "회차별 자세 판정",
                "verbose_name_plural": "회차별 자세 판정",
                "ordering": ["job", "seq"],
                "constraints": [models.UniqueConstraint(fields=("job", "seq"), name="uniq_job_rep_seq")],
            },
        ),
    ]
