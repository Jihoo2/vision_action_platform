from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import page_views
from .views import AnalysisJobViewSet

router = DefaultRouter()
router.register("analyses", AnalysisJobViewSet, basename="analysis")

urlpatterns = [
    path("api/v1/", include(router.urls)),
    path("analyses/", page_views.analyses_index, name="analyses_index"),
    path("dashboard/", page_views.dashboard, name="dashboard"),
]
