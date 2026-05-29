import importlib.util
from datetime import timedelta
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from anomaly.ml.service import clear_model_cache, default_model_path
from telemetry.models import TelemetryReading


class Command(BaseCommand):
    help = 'Train the anomaly model from Django telemetry history.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90)
        parser.add_argument('--limit', type=int, default=50000)
        parser.add_argument('--min-rows', type=int, default=500)
        parser.add_argument('--contamination', type=float, default=0.03)
        parser.add_argument('--n-jobs', type=int, default=1)
        parser.add_argument('--output', default=str(default_model_path()))

    def handle(self, *args, **options):
        try:
            from django.utils import timezone

            since = timezone.now() - timedelta(days=options['days'])
            queryset = (
                TelemetryReading.objects
                .filter(timestamp__gte=since)
                .exclude(current__isnull=True)
                .order_by('-timestamp')[:options['limit']]
            )

            rows = [
                {
                    'current': reading.current,
                    'pir': reading.pir,
                    'timestamp': reading.timestamp,
                }
                for reading in queryset
            ]
            history = pd.DataFrame(rows)
        except Exception as exc:
            raise CommandError(f'Unable to load telemetry history: {exc}') from exc

        try:
            trainer_path = Path(settings.BASE_DIR).parent / 'ML' / 'scripts' / 'train_phantom_current_model.py'
            spec = importlib.util.spec_from_file_location('train_phantom_current_model', trainer_path)
            trainer = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(trainer)
        except Exception as exc:
            raise CommandError(f'Unable to import trainer: {exc}') from exc

        try:
            model_path = trainer.train_from_frame(
                history=history,
                output_path=options['output'],
                contamination=options['contamination'],
                n_jobs=options['n_jobs'],
                min_rows=options['min_rows'],
                training_source='database',
            )
        except Exception as exc:
            raise CommandError(f'Production training failed: {exc}') from exc

        clear_model_cache()
        self.stdout.write(self.style.SUCCESS(
            f"Production model saved to {model_path} from {len(history)} telemetry rows."
        ))
