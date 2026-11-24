"""이미 수집된 IP Webcam 영상(mp4v)을 브라우저 재생용 H.264 로 일괄 변환

    python manage.py convert_captures           # 변환
    python manage.py convert_captures --dry-run # 대상만 확인
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from analyses.camera_capture import to_h264, video_codec
from analyses.models import AnalysisJob


class Command(BaseCommand):
    help = "IP Webcam 수집 영상을 H.264 로 변환 (미리보기 재생용)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dry_run=False, **opts):
        done = skipped = missing = failed = 0
        jobs = AnalysisJob.objects.filter(input_type="IPCAM").exclude(video="").order_by("pk")
        for job in jobs:
            path = Path(settings.MEDIA_ROOT) / job.video.name
            if not path.exists():
                missing += 1
                self.stdout.write(f"#{job.pk} 파일 없음: {job.video.name}")
                continue
            codec = video_codec(path)
            if codec == "h264":
                skipped += 1
                continue
            if dry_run:
                self.stdout.write(f"#{job.pk} 변환 대상 ({codec})")
                continue
            if to_h264(path):
                done += 1
                self.stdout.write(self.style.SUCCESS(f"#{job.pk} {codec} → h264"))
            else:
                failed += 1
                self.stdout.write(self.style.ERROR(f"#{job.pk} 변환 실패"))
        self.stdout.write(f"변환 {done} · 이미 h264 {skipped} · 파일 없음 {missing} · 실패 {failed}")
