# Smart Home Anomaly Detection

This service uses a scikit-learn `IsolationForest` model to detect phantom
current in smart home energy readings.

## Features

- `current`: measured current for the monitored device or circuit.
- `pir`: occupancy signal, where `1` means motion detected and `0` means no motion.
- `hour_of_day`: local hour from `0` to `23`.

## Train From Supabase

Recommended production training uses the Django telemetry table:

```powershell
python Backend\manage.py train_anomaly_model --days 90 --min-rows 500
```

You can also train from a custom Supabase/Postgres table through `DATABASE_URL`:

```powershell
python ML\scripts\train_phantom_current_model.py `
  --table sensor_history `
  --current-column current `
  --pir-column pir `
  --timestamp-column timestamp `
  --min-rows 500
```

The default model artifact is written to:

```text
Backend/anomaly/models/phantom_current_iforest.joblib
```

For local development before Supabase has enough telemetry, create a bootstrap
artifact from deterministic synthetic sensor patterns:

```powershell
python ML\scripts\train_phantom_current_model.py --synthetic
```

Synthetic artifacts are useful for local smoke tests only. Production artifacts
should report `"training_source": "database"` from `/api/anomaly/status/`.

## Production Validation

Before deploying or restarting the API, validate the artifact:

```powershell
python Backend\manage.py validate_anomaly_model --require-production
```

The same status is available over HTTP:

```text
GET /api/anomaly/status/
```

Production is ready when `ready` and `production_ready` are both `true`.

## Predict

POST JSON to:

```text
/api/anomaly/phantom-current/
```

Example body:

```json
{
  "current": 0.42,
  "pir": 0,
  "hour_of_day": 23,
  "voltage": 230,
  "sample_window_minutes": 1
}
```

The API returns anomaly status, confidence score, IsolationForest decision score,
and estimated phantom energy waste.
