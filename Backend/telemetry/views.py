from django.http import JsonResponse
from .models import TelemetryReading

def get_latest_telemetry(request):
    from django.db import close_old_connections
    from devices.models import Device
    from accounts.views import get_user_from_jwt
    try:
        close_old_connections()
        
        # Authenticate using Bearer token
        user = get_user_from_jwt(request)
        if not user:
            return JsonResponse({
                "gas": 0,
                "current": 0,
                "flame": 1,
                "status": "SAFE",
                "timestamp": None,
                "device_mac": None,
                "device_name": "No Account Connected"
            })
            
        # Get devices registered to this user
        user_devices = Device.objects.filter(owner=user, is_paired=True)
        if not user_devices.exists():
            return JsonResponse({
                "gas": 0,
                "current": 0,
                "flame": 1,
                "status": "SAFE",
                "timestamp": None,
                "device_mac": None,
                "device_name": "No Devices Registered"
            })

        latest_readings = []
        for dev in user_devices:
            try:
                # Find the latest reading for each paired device
                r = TelemetryReading.objects.filter(device=dev).latest('id')
                
                # Only consider it active if seen in the last 15 seconds
                from django.utils import timezone
                if (timezone.now() - r.timestamp).total_seconds() < 15:
                    latest_readings.append(r)
            except TelemetryReading.DoesNotExist:
                continue

        if not latest_readings:
            # Fallback to the absolute latest reading if no active ones in the last 15 seconds
            try:
                latest = TelemetryReading.objects.filter(device__in=user_devices).latest('id')
                latest_readings = [latest]
            except TelemetryReading.DoesNotExist:
                return JsonResponse({
                    "gas": 0,
                    "current": 0,
                    "flame": 1,
                    "status": "SAFE",
                    "timestamp": None,
                    "device_mac": None,
                    "device_name": "No Active Telemetry"
                })

        # Aggregate values across active devices
        max_gas = max(r.gas for r in latest_readings)
        min_flame = min(r.flame for r in latest_readings) # Active-LOW: 0 means fire, 1 means safe
        max_current = max(r.current for r in latest_readings)
        
        # Propagate warning statuses if any active device has it
        status = "SAFE"
        for r in latest_readings:
            if r.status in ["GAS_LEAK", "FIRE_EMERGENCY", "OVERCURRENT_TRIP"]:
                status = r.status
                break

        # Use the absolute latest reading to populate metadata (mac, name, timestamp)
        absolute_latest = max(latest_readings, key=lambda r: r.id)

        data = {
            "gas": max_gas,
            "current": max_current,
            "flame": min_flame,
            "status": status,
            "timestamp": absolute_latest.timestamp.isoformat(),
            "device_mac": absolute_latest.device.mac_address,
            "device_name": absolute_latest.device.name
        }
    except Exception as e:
        print(f"Error fetching latest telemetry: {e}")
        data = {
            "gas": 0,
            "current": 0,
            "flame": 1,
            "status": "SAFE",
            "timestamp": None,
            "device_mac": None,
            "device_name": "No Active Telemetry"
        }
    return JsonResponse(data)
