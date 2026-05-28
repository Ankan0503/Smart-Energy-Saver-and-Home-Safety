from django.urls import path
from .views import get_latest_telemetry

urlpatterns = [
    path('latest/', get_latest_telemetry, name='latest_telemetry'),
]
