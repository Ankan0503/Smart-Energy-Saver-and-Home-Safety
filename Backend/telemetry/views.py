from django.http import JsonResponse
from django.db.models import Q
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
                "power": 0,
                "pir": 1,
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
                "power": 0,
                "pir": 1,
                "flame": 1,
                "status": "SAFE",
                "timestamp": None,
                "device_mac": None,
                "device_name": "No Devices Registered"
            })

        latest_readings = []
        for dev in user_devices:
            try:
                # Prefer the device FK, but include legacy id/mac rows.
                r = TelemetryReading.objects.filter(
                    Q(device_ref=dev) | Q(device_id=dev.mac_address) | Q(device_id=str(dev.id))
                ).latest('id')
                
                # Only consider it active if seen in the last 15 seconds
                from django.utils import timezone
                if (timezone.now() - r.timestamp).total_seconds() < 15:
                    latest_readings.append(r)
            except TelemetryReading.DoesNotExist:
                continue

        if not latest_readings:
            # Fallback to the absolute latest reading if no active ones in the last 15 seconds
            try:
                legacy_ids = [str(d.id) for d in user_devices]
                mac_ids = [d.mac_address for d in user_devices]
                latest = TelemetryReading.objects.filter(
                    Q(device_ref__in=user_devices) | Q(device_id__in=legacy_ids) | Q(device_id__in=mac_ids)
                ).latest('id')
                latest_readings = [latest]
            except TelemetryReading.DoesNotExist:
                return JsonResponse({
                    "gas": 0,
                    "current": 0,
                    "power": 0,
                    "pir": 1,
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
        max_power = max(r.power for r in latest_readings)
        min_pir = min(r.pir for r in latest_readings) # 0 means at least one active device reports no occupancy
        
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
            "power": max_power,
            "pir": min_pir,
            "flame": min_flame,
            "status": status,
            "timestamp": absolute_latest.timestamp.isoformat(),
            "device_mac": absolute_latest.device_ref.mac_address if absolute_latest.device_ref else absolute_latest.device_id,
            "device_name": absolute_latest.device_ref.name if absolute_latest.device_ref else absolute_latest.device_id
        }
    except Exception as e:
        print(f"Error fetching latest telemetry: {e}")
        data = {
            "gas": 0,
            "current": 0,
            "power": 0,
            "pir": 1,
            "flame": 1,
            "status": "SAFE",
            "timestamp": None,
            "device_mac": None,
            "device_name": "No Active Telemetry"
        }
    return JsonResponse(data)

def debug_telemetry(request):
    readings = TelemetryReading.objects.all().order_by('-id')[:40]
    data = []
    for r in readings:
        pred = getattr(r, 'prediction', None)
        data.append({
            "id": r.id,
            "device_id": r.device_id,
            "appliance_id": r.appliance_id,
            "appliance_name": r.appliance.name if r.appliance else "Global",
            "current": r.current,
            "power": r.power,
            "c1": r.c1,
            "c2": r.c2,
            "c3": r.c3,
            "c4": r.c4,
            "predicted_state": pred.predicted_state if pred else "N/A",
            "action_taken": pred.action_taken if pred else "",
            "reason": pred.reason if pred else "",
            "timestamp": r.timestamp.isoformat()
        })
    return JsonResponse({"readings": data})
