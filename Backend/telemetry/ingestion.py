import hashlib
import json
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from anomaly.ml.appliance_state import predict_log_and_act
from devices.models import Device

from .models import TelemetryReading


def _float_value(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_value(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def payload_hash(payload: dict) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def ingest_telemetry_payload(data: dict) -> tuple[TelemetryReading, object | None]:
    mac = data.get('mac') or data.get('device_id') or data.get('device')
    if not mac:
        raise ValueError('Telemetry payload requires mac or device_id.')

    device, _ = Device.objects.get_or_create(
        mac_address=mac,
        defaults={
            'name': 'Unassigned Sensor Node',
            'role': 'sensor',
            'is_paired': False,
        },
    )
    device.save()

    current = _float_value(data.get('current'), 0.0)
    voltage = _float_value(data.get('voltage'), getattr(settings, 'APPLIANCE_DEFAULT_VOLTAGE', 230.0))
    power = _float_value(data.get('power'), current * voltage)
    timestamp = data.get('timestamp')

    reading = TelemetryReading.objects.create(
        device_ref=device,
        device_id=mac,
        gas=_int_value(data.get('gas'), 0),
        current=current,
        power=power,
        pir=1 if _int_value(data.get('pir'), 1) else 0,
        flame=_int_value(data.get('flame'), 1),
        status=str(data.get('status') or 'SAFE')[:50],
    )

    if timestamp:
        parsed = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
        reading.timestamp = parsed
        reading.save(update_fields=['timestamp'])

    prediction = predict_log_and_act(reading)
    return reading, prediction
