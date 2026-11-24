# Django가 시작될 때 Celery 앱도 함께 로드 → @shared_task 가 이 앱에 등록됨
from .celery import app as celery_app

__all__ = ("celery_app",)
