from django.http import JsonResponse
from .models import TelemetryReading

def get_latest_telemetry(request):
    try:
        latest = TelemetryReading.objects.latest('id')
        data = {
            "gas": latest.gas,
            "current": latest.current,
            "flame": latest.flame,
            "status": latest.status,
            "timestamp": latest.timestamp.isoformat()
        }
    except TelemetryReading.DoesNotExist:
        data = {
            "gas": 0,
            "current": 0,
            "flame": 1,
            "status": "SAFE",
            "timestamp": None
        }
    return JsonResponse(data)
