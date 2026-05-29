# ML Deployment Checklist

Use this checklist when deploying the phantom-current model with the Django API.

## 1. Install Dependencies

```powershell
pip install -r Backend\requirements.txt
```

## 2. Apply Database Migrations

```powershell
python Backend\manage.py migrate
```

This includes `telemetry.0004_telemetryreading_pir`, which stores occupancy for
model predictions.

## 3. Train A Production Artifact

Train from real Django telemetry history:

```powershell
python Backend\manage.py train_anomaly_model --days 90 --min-rows 500
```

Alternatively, train from a custom Supabase/Postgres table. The table must
include current, PIR, and timestamp columns.

```powershell
python ML\scripts\train_phantom_current_model.py `
  --database-url "%DATABASE_URL%" `
  --table sensor_history `
  --current-column current `
  --pir-column pir `
  --timestamp-column timestamp `
  --min-rows 500 `
  --output Backend\anomaly\models\phantom_current_iforest.joblib
```

Do not deploy a `--synthetic` artifact as the production model.

## 4. Configure Environment

Set these in the backend runtime:

```text
ANOMALY_MODEL_PATH=Backend/anomaly/models/phantom_current_iforest.joblib
ANOMALY_DEFAULT_VOLTAGE=230
PHANTOM_BASELINE_CURRENT=0
```

Use an absolute `ANOMALY_MODEL_PATH` if your host runs Django from a different
working directory.

## 5. Validate The Artifact

```powershell
python Backend\manage.py validate_anomaly_model --require-production
```

The command must pass before deployment. You can also verify:

```text
GET /api/anomaly/status/
```

Expected production status:

```json
{
  "ready": true,
  "production_ready": true,
  "training_source": "database"
}
```

## 6. Smoke Test Prediction

```powershell
python Backend\manage.py shell -c "from anomaly.ml.service import predict_phantom_current; print(predict_phantom_current({'current':0.65,'pir':0,'hour_of_day':23})['anomaly_type'])"
```

Expected output for this synthetic smoke sample:

```text
PHANTOM_CURRENT
```

## 7. Deploy Firmware With PIR

The current firmware reads PIR from GPIO `33` on gateway and subnode. Update
`PIR_PIN` before flashing if your wiring uses another pin.
