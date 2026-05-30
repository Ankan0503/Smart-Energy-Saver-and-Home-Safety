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


STATE_ACTIVE = 'ACTIVE'
STATE_IDLE = 'IDLE'
STATE_PHANTOM_LOAD = 'PHANTOM_LOAD'
STATE_ABNORMAL = 'ABNORMAL'
STATE_ORDER = [STATE_ACTIVE, STATE_IDLE, STATE_PHANTOM_LOAD, STATE_ABNORMAL]
FEATURE_COLUMNS = [
    'current',
    'power',
    'pir',
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
        'pir': 1 if int(reading.pir or 0) else 0,
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


def fallback_prediction(reading: TelemetryReading) -> tuple[str, float, str]:
    current = float(reading.current or 0.0)
    power = float(reading.power or 0.0)
    pir = 1 if int(reading.pir or 0) else 0

    if pir == 0 and power > 20:
        return STATE_IDLE, 0.72, 'Fallback logic: sustained load while unoccupied.'
    if pir == 0 and 3 <= power <= 20:
        return STATE_PHANTOM_LOAD, 0.76, 'Fallback logic: low standby draw while unoccupied.'
    if power > 1800 or current > 8:
        return STATE_ABNORMAL, 0.68, 'Fallback logic: unusually high load detected.'
    if power > 20:
        return STATE_ACTIVE, 0.7, 'Fallback logic: occupied or meaningful active load.'
    return STATE_IDLE, 0.62, 'Fallback logic: low load idle state.'


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


def should_cutoff(reading: TelemetryReading, predicted_state: str) -> tuple[bool, str]:
    if not getattr(settings, 'APPLIANCE_CUTOFF_ENABLED', True):
        return False, 'Automatic cutoff disabled.'
    if predicted_state not in {STATE_IDLE, STATE_PHANTOM_LOAD}:
        return False, 'Predicted state does not require cutoff.'
    if int(reading.pir or 0) != 0:
        return False, 'Occupancy detected.'

    cutoff_seconds = int(getattr(settings, 'APPLIANCE_IDLE_CUTOFF_SECONDS', 300))
    since = reading.timestamp - timedelta(seconds=cutoff_seconds)
    recent = TelemetryReading.objects.filter(
        device_id=reading.device_id,
        timestamp__gte=since,
        timestamp__lte=reading.timestamp,
    )
    if recent.filter(pir=1).exists():
        return False, 'Recent occupancy detected inside cutoff window.'
    if not recent.exists():
        return False, 'Insufficient history for cutoff decision.'

    return True, f'No occupancy for {cutoff_seconds} seconds and state={predicted_state}.'


def publish_cutoff_command(reading: TelemetryReading) -> str:
    import os
    import ssl

    broker = os.getenv('MQTT_BROKER', 'broker.hivemq.com')
    port = int(os.getenv('MQTT_PORT', 1883))
    username = os.getenv('MQTT_USER')
    password = os.getenv('MQTT_PASSWORD')
    topic = getattr(settings, 'APPLIANCE_CUTOFF_COMMAND_TOPIC', 'aether/relay/command')

    auth = {'username': username, 'password': password} if username and password else None
    tls = {'ca_certs': None, 'cert_reqs': ssl.CERT_NONE, 'tls_version': ssl.PROTOCOL_TLS} if port == 8883 else None
    payload = {
        'relay': 'OFF',
        'device_id': reading.device_id,
        'mac': reading.device_id,
        'reason': 'unnecessary_power_consumption',
    }
    mqtt_publish.single(topic, payload=json.dumps(payload), hostname=broker, port=port, auth=auth, tls=tls)
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
