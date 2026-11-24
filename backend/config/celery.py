"""Celery 앱 — Django 설정(CELERY_*)을 읽고 각 앱의 tasks.py 를 자동 탐색

Worker 실행:  cd backend && celery -A config worker -l info
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
