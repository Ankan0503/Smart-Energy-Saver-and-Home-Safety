from functools import lru_cache
from pathlib import Path
from typing import Any
from datetime import timedelta
import json

import joblib
import pandas as pd
from django.conf import settings
from django.db.models import Avg, Max
from django.utils import timezone
from paho.mqtt import publish as mqtt_publish

from telemetry.models import ApplianceStatePrediction, TelemetryReading

# In-memory store for tracking when each appliance channel was turned ON (active)
_ACTIVATION_TIMES = {}

def record_activation(appliance_id: int, timestamp=None):
    _ACTIVATION_TIMES[appliance_id] = timestamp or timezone.now()

def get_activation_time(appliance_id: int):
    return _ACTIVATION_TIMES.get(appliance_id)

def clear_activation(appliance_id: int):
    _ACTIVATION_TIMES.pop(appliance_id, None)


STATE_ACTIVE = 'ACTIVE'
STATE_IDLE = 'IDLE'
STATE_PHANTOM_LOAD = 'PHANTOM_LOAD'
STATE_ABNORMAL = 'ABNORMAL'
STATE_ORDER = [STATE_ACTIVE, STATE_IDLE, STATE_PHANTOM_LOAD, STATE_ABNORMAL]
FEATURE_COLUMNS = [
    'current',
    'power',
    'hour_of_day',
    'day_of_week',
    'device_avg_power',
    'device_max_power',
    'power_to_avg_ratio',
    'device_id',
]


class ApplianceModelNotReady(RuntimeError):
    pass


def model_path() -> Path:
    return Path(getattr(settings, 'APPLIANCE_STATE_MODEL_PATH'))


def telemetry_to_features(reading: TelemetryReading) -> pd.DataFrame:
    ts = timezone.localtime(reading.timestamp)
    stats = TelemetryReading.objects.filter(device_id=reading.device_id).aggregate(
        avg_power=Avg('power'),
        max_power=Max('power'),
    )
    avg_power = float(stats['avg_power'] or reading.power or 0.0)
    max_power = float(stats['max_power'] or reading.power or 0.0)
    ratio = float(reading.power or 0.0) / max(avg_power, 1e-6)

    return pd.DataFrame([{
        'current': float(reading.current or 0.0),
        'power': float(reading.power or 0.0),
        'hour_of_day': int(ts.hour),
        'day_of_week': int(ts.weekday()),
        'device_avg_power': avg_power,
        'device_max_power': max_power,
        'power_to_avg_ratio': ratio,
        'device_id': reading.device_id,
    }], columns=FEATURE_COLUMNS)


@lru_cache(maxsize=1)
def load_appliance_model() -> dict:
    path = model_path()
    if not path.exists():
        raise ApplianceModelNotReady(f'Appliance state model not found at {path}')
    bundle = joblib.load(path)
    if not isinstance(bundle, dict) or 'pipeline' not in bundle or 'features' not in bundle:
        raise ApplianceModelNotReady('Invalid appliance state model artifact.')
    if list(bundle['features']) != FEATURE_COLUMNS:
        raise ApplianceModelNotReady('Appliance state model feature schema mismatch.')
    return bundle


def clear_appliance_model_cache():
    load_appliance_model.cache_clear()


def appliance_model_status() -> dict:
    path = model_path()
    status = {'ready': False, 'model_path': str(path), 'exists': path.exists()}
    try:
        bundle = load_appliance_model()
    except ApplianceModelNotReady as exc:
        status['error'] = str(exc)
        return status
    status.update({
        'ready': True,
        'model_version': bundle.get('model_version'),
        'trained_at': bundle.get('trained_at'),
        'training_rows': bundle.get('training_rows'),
        'features': bundle.get('features'),
    })
    return status



def predict_appliance_state(reading: TelemetryReading) -> dict[str, Any]:
    features = telemetry_to_features(reading)
    try:
        bundle = load_appliance_model()
        pipeline = bundle['pipeline']
        predicted_state = str(pipeline.predict(features)[0])
        confidence = 0.0
        if hasattr(pipeline, 'predict_proba'):
            probabilities = pipeline.predict_proba(features)[0]
            confidence = float(max(probabilities))
        reason = 'RandomForest appliance behavior model prediction.'
        model_version = bundle.get('model_version', 'unknown')
    except ApplianceModelNotReady as exc:
        predicted_state, confidence, reason = fallback_prediction(reading)
        model_version = 'fallback'
        reason = f'{reason} {exc}'

    return {
        'predicted_state': predicted_state,
        'confidence_score': round(confidence, 4),
        'reason': reason,
        'features': features.iloc[0].to_dict(),
        'model_version': model_version,
    }


def fallback_prediction(reading: TelemetryReading) -> tuple[str, float, str]:
    current = float(reading.current or 0.0)
    power = float(reading.power or 0.0)
    ts = timezone.localtime(reading.timestamp)
    hour = ts.hour

    # 1. Peak Surge / Overcurrent Anomaly
    if power > 2300 or current > 10.0:
        return STATE_ABNORMAL, 0.95, 'Overcurrent surge: unsafe heavy load limit breached.'
    
    # 2. Time-of-day Standby Load (1:00 AM - 5:00 AM)
    if (1 <= hour <= 5) and (3.0 <= power <= 25.0):
        return STATE_PHANTOM_LOAD, 0.88, 'Time-of-day anomaly: standby power drawn during sleeping hours.'
        
    # 3. Active Load
    if power > 25.0:
        return STATE_ACTIVE, 0.85, 'Normal active appliance consumption.'

    # 4. Low Standby / Idle State
    if 3.0 <= power <= 25.0:
        return STATE_PHANTOM_LOAD, 0.75, 'Standby idle state.'
        
    return STATE_IDLE, 0.62, 'Device turned off.'


def should_cutoff(reading: TelemetryReading, predicted_state: str) -> tuple[bool, str]:
    if not getattr(settings, 'APPLIANCE_CUTOFF_ENABLED', True):
        return False, 'Automatic cutoff disabled.'
    if predicted_state not in {STATE_PHANTOM_LOAD, STATE_IDLE}:
        return False, 'Predicted state does not require cutoff.'
    if not reading.appliance:
        return False, 'Global telemetry reading does not trigger cutoff.'
    if not reading.appliance.active:
        return False, 'Appliance is already turned off.'

    import os
    from dotenv import load_dotenv
    load_dotenv()
    cutoff_seconds = int(os.getenv('APPLIANCE_IDLE_CUTOFF_SECONDS', 300))

    # Check activation safety window to prevent immediately shutting off a newly turned on relay
    activation_time = get_activation_time(reading.appliance_id)
    if not activation_time:
        # If active in DB but no record in memory, initialize it now with current timestamp
        record_activation(reading.appliance_id, reading.timestamp)
        activation_time = reading.timestamp

    time_since_activation = (reading.timestamp - activation_time).total_seconds()
    if time_since_activation < cutoff_seconds:
        return False, f'Appliance was recently turned on ({int(time_since_activation)}s ago).'
    
    # Check if this appliance/channel is a light or charger
    app_type = (reading.appliance.type or '').lower()
    app_name = (reading.appliance.name or '').lower()
    is_exempt_when_drawing = (
        'light' in app_type or 'light' in app_name or
        'charger' in app_type or 'charger' in app_name
    )
    if is_exempt_when_drawing:
        # Exempt from auto-cutoff only if actively drawing power (turned ON and plugged in)
        if float(reading.power or 0.0) > 0.0:
            return False, 'Lights and chargers are exempt from auto-cutoff when drawing power.'

    since = reading.timestamp - timezone.timedelta(seconds=cutoff_seconds)
    
    # Look at recent readings for this specific appliance channel
    recent = TelemetryReading.objects.filter(
        device_id=reading.device_id,
        appliance_id=reading.appliance_id,
        timestamp__gte=since,
        timestamp__lte=reading.timestamp,
    )
    if not recent.exists():
        return False, 'Insufficient history for cutoff decision.'
        
    # Ensure we have telemetry spanning the full duration of the window
    oldest = recent.order_by('timestamp').first()
    # For short cutoff windows (e.g. 20s), we adjust the historical range check buffer
    buffer_seconds = min(20, int(cutoff_seconds * 0.6))
    if oldest.timestamp > since + timezone.timedelta(seconds=buffer_seconds):
        return False, 'Insufficient historical range to confirm continuous idle state.'
        
    # If the appliance was active (power > 25W) at any point, do not cutoff
    active_readings = recent.filter(power__gt=25.0)
    if active_readings.exists():
        return False, 'Appliance had active load inside cutoff window.'

    return True, f'Appliance has been idle (standby load) continuously for {cutoff_seconds} seconds.'


def publish_cutoff_command(reading: TelemetryReading) -> str:
    import os
    import ssl

    broker = os.getenv('MQTT_BROKER', 'broker.hivemq.com')
    port = int(os.getenv('MQTT_PORT', 1883))
    username = os.getenv('MQTT_USER')
    password = os.getenv('MQTT_PASSWORD')
    
    # Send control command to pairing/command topic
    topic = 'aether/pairing/command'

    auth = {'username': username, 'password': password} if username and password else None
    tls = {'ca_certs': None, 'cert_reqs': ssl.CERT_NONE, 'tls_version': ssl.PROTOCOL_TLS} if port == 8883 else None
    
    # Resolve channel ID and MAC for the subnode relay control
    payload = {
        'mac': reading.device.mac_address if reading.device else reading.device_id,
        'action': 'CONTROL_RELAY',
        'channel': reading.appliance.channel if reading.appliance else 1,
        'state': False  # Turn OFF
    }
    
    mqtt_publish.single(topic, payload=json.dumps(payload), hostname=broker, port=port, auth=auth, tls=tls)
    print(f"📡 Dynamic Auto-Cutoff published to MQTT: {payload}")
    return topic


def predict_log_and_act(reading: TelemetryReading) -> ApplianceStatePrediction:
    if hasattr(reading, 'prediction'):
        return reading.prediction

    result = predict_appliance_state(reading)
    predicted_state = result['predicted_state']
    action_taken = ''
    cutoff, cutoff_reason = should_cutoff(reading, predicted_state)
    reason = f"{result['reason']} {cutoff_reason}".strip()

    if cutoff:
        try:
            topic = publish_cutoff_command(reading)
            action_taken = f'RELAY_OFF:{topic}'
            reason = f'{reason} Automatic power cutoff executed.'
            # Mark the appliance channel as inactive in the database
            if reading.appliance:
                reading.appliance.active = False
                reading.appliance.save()
                clear_activation(reading.appliance_id)
        except Exception as exc:
            action_taken = 'CUTOFF_FAILED'
            reason = f'{reason} MQTT cutoff failed: {exc}'

    return ApplianceStatePrediction.objects.create(
        telemetry=reading,
        device_ref=reading.device_ref,
        device_id=reading.device_id,
        predicted_state=predicted_state,
        confidence_score=result['confidence_score'],
        action_taken=action_taken,
        reason=reason,
    )
