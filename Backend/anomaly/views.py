import json

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .ml.service import ModelNotReadyError, model_status, predict_phantom_current


@require_GET
def anomaly_model_status(request):
    status = model_status()
    response_status = 200 if status['ready'] else 503
    return JsonResponse(status, status=response_status)


@csrf_exempt
@require_POST
def detect_phantom_current(request):
    """
    REST endpoint for low-latency phantom current detection.

    Expected JSON:
    {
      "current": 0.42,
      "pir": 0,
      "hour_of_day": 23,
      "voltage": 230,
      "sample_window_minutes": 1
    }
    """
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        payload.setdefault('hour_of_day', timezone.localtime().hour)
        result = predict_phantom_current(payload)
        return JsonResponse(result)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Request body must be valid JSON.'}, status=400)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except ModelNotReadyError as exc:
        return JsonResponse({
            'error': str(exc),
            'hint': 'Train a production model from database telemetry before deployment.',
        }, status=503)
