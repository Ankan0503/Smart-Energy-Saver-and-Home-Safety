import hashlib
import json
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from anomaly.ml.socket_state import predict_socket_log_and_act
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


def _bool_value(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {'1', 'true', 'on', 'yes'}


def payload_hash(payload: dict) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def ingest_telemetry_payload(data: dict) -> tuple[TelemetryReading, object | None]:
    mac = data.get('mac') or data.get('device_id') or data.get('device')
    if not mac:
        raise ValueError('Telemetry payload requires mac or device_id.')

    # Determine role: if c1-c4 is in payload or MAC matches the relay MAC, it's a relay node
    role = "sensor"
    name = "Sensor Node"
    if "c1" in data or "c2" in data or "c3" in data or "c4" in data or mac == "70:4B:CA:27:78:84":
        role = "relay"
        name = "ESP32 Relay Node"

    device, _ = Device.objects.get_or_create(
        mac_address=mac,
        defaults={
            'name': f'Unassigned {name}',
            'role': role,
            'is_paired': False,
        },
    )
    
    if device.role != role:
        device.role = role
        device.name = f"Unassigned {name}"
    device.save()

    # Auto-create 3 default appliance sockets for relay nodes if missing.
    if device.role == 'relay':
        from devices.models import Appliance
        default_names = ["Socket 1", "Socket 2", "Socket 3"]
        default_types = ["Appliance", "Appliance", "Appliance"]
        default_consumptions = [100, 100, 100]
        for ch in range(1, 4):
            Appliance.objects.get_or_create(
                device=device,
                channel=ch,
                defaults={
                    "name": default_names[ch - 1],
                    "type": default_types[ch - 1],
                    "nominal_consumption": default_consumptions[ch - 1]
                }
            )

    voltage = _float_value(data.get('voltage'), getattr(settings, 'APPLIANCE_DEFAULT_VOLTAGE', 230.0))
    timestamp = data.get('timestamp')

    c1 = _float_value(data.get("c1"), 0.0)
    c2 = _float_value(data.get("c2"), 0.0)
    c3 = _float_value(data.get("c3"), 0.0)
    c4 = _float_value(data.get("c4"), 0.0)

    # Recalculate combined current and power from all four relay sockets.
    if device.role == 'relay':
        current = c1 + c2 + c3 + c4
    else:
        current = _float_value(data.get('current'), 0.0)
        
    power = current * voltage

    # 1. Save the overall/combined device telemetry reading
    reading = TelemetryReading.objects.create(
        device_ref=device,
        device_id=mac,
        appliance_id=None,
        channel=None,
        socket_id=None,
        gas=_int_value(data.get('gas'), 0),
        current=current,
        power=power,
        pir=1 if _int_value(data.get('pir'), 1) else 0,
        flame=_int_value(data.get('flame'), 1),
        status=str(data.get('status') or 'SAFE')[:50],
        c1=c1,
        c2=c2,
        c3=c3,
        c4=c4,
    )

    if timestamp:
        parsed = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
        reading.timestamp = parsed
        reading.save(update_fields=['timestamp'])

    # 2. Save individual telemetry readings for each socket on the relay node.
    socket_prediction = None
    if device.role == 'relay':
        from devices.models import Appliance
        appliances = Appliance.objects.filter(device=device, channel__in=[1, 2, 3])
        channel_currents = {
            1: c1,
            2: c2,
            3: c3
        }
        for app in appliances:
            app_current = channel_currents.get(app.channel, 0.0)
            relay_state_key = f'r{app.channel}'
            relay_is_on = app.active
            if relay_state_key in data:
                relay_is_on = _bool_value(data.get(relay_state_key), app.active)
                app.active = relay_is_on
                app.save(update_fields=['active'])
            elif app_current > 0.0 and not app.active:
                relay_is_on = True
                app.active = True
                app.save(update_fields=['active'])

            app_reading = TelemetryReading.objects.create(
                device_ref=device,
                device_id=mac,
                appliance_id=app.id,
                channel=app.channel,
                socket_id=app.channel,
                gas=_int_value(data.get('gas'), 0),
                current=app_current,  # Mapped individual current
                power=app_current * voltage,
                pir=1 if _int_value(data.get('pir'), 1) else 0,
                flame=_int_value(data.get('flame'), 1),
                status=('ON' if relay_is_on else 'OFF'),
                c1=c1,
                c2=c2,
                c3=c3,
                c4=c4,
            )
            if timestamp:
                app_reading.timestamp = parsed
                app_reading.save(update_fields=['timestamp'])
            
            if relay_is_on:
                socket_prediction = predict_socket_log_and_act(mac, app.channel)

    return reading, socket_prediction
