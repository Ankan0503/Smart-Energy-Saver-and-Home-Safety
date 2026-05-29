from django.urls import path

from .views import anomaly_model_status, detect_phantom_current


urlpatterns = [
    path('status/', anomaly_model_status, name='anomaly_model_status'),
    path('phantom-current/', detect_phantom_current, name='detect_phantom_current'),
]
