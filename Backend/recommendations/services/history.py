from datetime import timedelta

import pandas as pd
from django.conf import settings
from django.utils import timezone

from telemetry.models import TelemetryReading


def readings_from_database(days: int = 30, user=None, device_id=None) -> pd.DataFrame:
    """
    Load recent telemetry into a pandas DataFrame for lightweight analytics.

    The telemetry table stores current, PIR, device and timestamp so occupancy
    waste can be detected from live history as well as posted payloads.
    """
    since = timezone.now() - timedelta(days=days)
    queryset = (
        TelemetryReading.objects
        .select_related('device')
        .filter(timestamp__gte=since)
        .order_by('timestamp')
    )

    if user is not None:
        queryset = queryset.filter(device__owner=user, device__is_paired=True)
    if device_id:
        queryset = queryset.filter(device_id=device_id)

    rows = []
    voltage = float(getattr(settings, 'RECOMMENDATION_DEFAULT_VOLTAGE', 230.0))
    for reading in queryset:
        device_name = reading.device.name if reading.device else 'Unknown appliance'
        rows.append({
            'timestamp': reading.timestamp,
            'appliance': device_name,
            'device_id': reading.device_id,
            'current': float(reading.current or 0),
            'pir': 1 if int(reading.pir or 0) else 0,
            'power_watts': float(reading.current or 0) * voltage,
        })

    return pd.DataFrame(rows)


def readings_from_payload(readings: list[dict]) -> pd.DataFrame:
    """Convert posted sensor history into the normalized analytics frame."""
    return pd.DataFrame(readings or [])
