"""
Sample trainer for the smart home phantom-current IsolationForest model.

The script reads sensor history from Supabase Postgres using DATABASE_URL, builds a
scikit-learn preprocessing pipeline, trains IsolationForest, and writes a joblib
artifact consumed by the Django API.

Example:
    python ML/scripts/train_phantom_current_model.py \
        --table sensor_history \
        --current-column current \
        --pir-column pir \
        --timestamp-column timestamp

Development bootstrap:
    python ML/scripts/train_phantom_current_model.py --synthetic
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg2
import sklearn
from dotenv import load_dotenv
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


FEATURE_COLUMNS = ['current', 'hour_of_day']
IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    args = argparse.Namespace()
    parser = argparse.ArgumentParser(description='Train phantom-current anomaly detector.')
    parser.add_argument('--database-url', default=os.getenv('DATABASE_URL'), help='Supabase Postgres DATABASE_URL.')
    parser.add_argument('--table', default=os.getenv('SUPABASE_SENSOR_TABLE', 'sensor_history'))
    parser.add_argument('--current-column', default=os.getenv('SUPABASE_CURRENT_COLUMN', 'current'))
    parser.add_argument('--timestamp-column', default=os.getenv('SUPABASE_TIMESTAMP_COLUMN', 'timestamp'))
    parser.add_argument('--limit', type=int, default=int(os.getenv('TRAINING_ROW_LIMIT', '50000')))
    parser.add_argument('--min-rows', type=int, default=int(os.getenv('MIN_TRAINING_ROWS', '500')))
    parser.add_argument('--contamination', type=float, default=float(os.getenv('IFOREST_CONTAMINATION', '0.03')))
    parser.add_argument('--n-jobs', type=int, default=int(os.getenv('IFOREST_N_JOBS', '1')))
    parser.add_argument(
        '--synthetic',
        action='store_true',
        help='Train a deterministic bootstrap model from generated normal/phantom-current patterns.',
    )
    parser.add_argument(
        '--output',
        default=os.getenv(
            'ANOMALY_MODEL_PATH',
            str(project_root() / 'Backend' / 'anomaly' / 'models' / 'phantom_current_iforest.joblib'),
        ),
    )
    return parser.parse_args()


def generate_synthetic_history(rows: int) -> pd.DataFrame:
    """
    Create a deterministic bootstrap dataset for local development.

    Real deployments should train from Supabase history. This dataset keeps the
    API usable before enough sensor readings have accumulated.
    """
    sample_count = max(rows, 500)
    rng = np.random.default_rng(42)
    timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=sample_count, freq='min')
    hours = timestamps.hour.to_numpy()

    base_current = rng.choice([
        rng.normal(loc=0.42, scale=0.16, size=sample_count),
        rng.normal(loc=0.018, scale=0.018, size=sample_count)
    ], size=1)[0]

    evening_boost = ((hours >= 18) & (hours <= 23)) * rng.normal(0.18, 0.06, sample_count)
    current = np.clip(base_current + evening_boost, 0, None)

    anomaly_count = max(12, int(sample_count * 0.03))
    anomaly_indices = rng.choice(np.arange(sample_count), size=anomaly_count, replace=False)
    current[anomaly_indices] = rng.normal(loc=0.55, scale=0.12, size=anomaly_count).clip(0.25, 1.2)

    return pd.DataFrame({
        'current': current,
        'timestamp': timestamps,
    })


def load_history(args: argparse.Namespace) -> pd.DataFrame:
    if args.synthetic:
        return generate_synthetic_history(args.limit)

    if not args.database_url:
        raise RuntimeError('DATABASE_URL is required to read sensor history from Supabase. Use --synthetic for a local bootstrap model.')

    for value in [args.table, args.current_column, args.timestamp_column]:
        if not IDENTIFIER_RE.match(value):
            raise RuntimeError(f'Unsafe SQL identifier: {value}')

    query = f"""
        SELECT
            {args.current_column} AS current,
            {args.timestamp_column} AS timestamp
        FROM {args.table}
        WHERE {args.current_column} IS NOT NULL
          AND {args.timestamp_column} IS NOT NULL
        ORDER BY {args.timestamp_column} DESC
        LIMIT %s
    """

    with psycopg2.connect(args.database_url) as connection:
        return pd.read_sql_query(query, connection, params=(args.limit,))


def preprocess_history(history: pd.DataFrame, min_rows: int = 500) -> pd.DataFrame:
    if history.empty:
        raise RuntimeError('No training rows were returned for the selected training window.')

    frame = history.copy()
    frame['timestamp'] = pd.to_datetime(frame['timestamp'], utc=True, errors='coerce')
    frame['current'] = pd.to_numeric(frame['current'], errors='coerce')
    frame['hour_of_day'] = frame['timestamp'].dt.hour
    frame = frame.dropna(subset=FEATURE_COLUMNS)

    if len(frame) < min_rows:
        raise RuntimeError(f'At least {min_rows} clean rows are required; got {len(frame)}.')

    return frame[FEATURE_COLUMNS]


def build_pipeline(contamination: float, n_jobs: int = 1) -> Pipeline:
    # Scaling keeps feature magnitudes comparable before IsolationForest sees them.
    preprocessor = ColumnTransformer(
        transformers=[
            ('numeric', StandardScaler(), FEATURE_COLUMNS),
        ],
        remainder='drop',
    )

    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        max_samples='auto',
        random_state=42,
        n_jobs=n_jobs,
    )

    return Pipeline([
        ('preprocess', preprocessor),
        ('isolation_forest', model),
    ])


def train_from_frame(
    history: pd.DataFrame,
    output_path: str | Path,
    contamination: float = 0.03,
    n_jobs: int = 1,
    min_rows: int = 500,
    training_source: str = 'database',
) -> Path:
    training_frame = preprocess_history(history, min_rows)
    pipeline = build_pipeline(contamination, n_jobs)
    pipeline.fit(training_frame)

    scores = pipeline.decision_function(training_frame)
    negative_margins = np.abs(scores[scores < 0])
    score_reference = float(np.percentile(negative_margins, 95)) if len(negative_margins) else 0.05

    artifact = {
        'artifact_schema_version': 2,
        'pipeline': pipeline,
        'features': FEATURE_COLUMNS,
        'score_reference': max(score_reference, 1e-6),
        'trained_at': datetime.now(timezone.utc).isoformat(),
        'training_rows': int(len(training_frame)),
        'training_source': training_source,
        'library_versions': {
            'numpy': np.__version__,
            'pandas': pd.__version__,
            'scikit_learn': sklearn.__version__,
        },
        'model_version': datetime.now(timezone.utc).strftime('iforest-%Y%m%d%H%M%S'),
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, output_path)
    return output_path


def train() -> Path:
    load_dotenv(project_root() / 'Backend' / '.env')
    load_dotenv(project_root() / '.env')

    args = parse_args()
    history = load_history(args)
    return train_from_frame(
        history=history,
        output_path=args.output,
        contamination=args.contamination,
        n_jobs=args.n_jobs,
        min_rows=args.min_rows,
        training_source='synthetic' if args.synthetic else 'database',
    )


if __name__ == '__main__':
    try:
        model_path = train()
        print(f'Model saved to {model_path}')
    except Exception as exc:
        print(f'Training failed: {exc}', file=sys.stderr)
        sys.exit(1)
