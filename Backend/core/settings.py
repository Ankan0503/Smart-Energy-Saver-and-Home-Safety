import os
import dj_database_url # type: ignore
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')

DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'telemetry.apps.TelemetryConfig',
    'accounts.apps.AccountsConfig',
    'devices.apps.DevicesConfig',
    'anomaly.apps.AnomalyConfig',
    'recommendations.apps.RecommendationsConfig',
    'hazards.apps.HazardsConfig',
    'notifications.apps.NotificationsConfig',
]

MIDDLEWARE = [
    'telemetry.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default = os.getenv("DATABASE_URL"),
        conn_max_age = int(os.getenv("DATABASE_CONN_MAX_AGE", 0)), 
        ssl_require = True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


STATIC_URL = 'static/'

# Machine-learning service configuration. The artifact is produced by
# ML/scripts/train_phantom_current_model.py and loaded once per Django process.
ANOMALY_MODEL_PATH = os.getenv(
    'ANOMALY_MODEL_PATH',
    str(BASE_DIR / 'anomaly' / 'models' / 'phantom_current_iforest.joblib'),
)
ANOMALY_DEFAULT_VOLTAGE = float(os.getenv('ANOMALY_DEFAULT_VOLTAGE', 230.0))
PHANTOM_BASELINE_CURRENT = float(os.getenv('PHANTOM_BASELINE_CURRENT', 0.0))

# Energy recommendation engine defaults. Keep these environment-driven so
# deployments can tune thresholds for local tariffs and sensor calibration.
RECOMMENDATION_DEFAULT_VOLTAGE = float(os.getenv('RECOMMENDATION_DEFAULT_VOLTAGE', 230.0))
ELECTRICITY_RATE_PER_KWH = float(os.getenv('ELECTRICITY_RATE_PER_KWH', 8.0))
RECOMMENDATION_CURRENCY = os.getenv('RECOMMENDATION_CURRENCY', 'INR')
STANDBY_CURRENT_THRESHOLD = float(os.getenv('STANDBY_CURRENT_THRESHOLD', 0.05))
STANDBY_POWER_THRESHOLD_WATTS = float(os.getenv('STANDBY_POWER_THRESHOLD_WATTS', 8.0))
ABNORMAL_USAGE_TREND_PERCENT = float(os.getenv('ABNORMAL_USAGE_TREND_PERCENT', 25.0))
MIN_RECOMMENDATION_SAMPLES = int(os.getenv('MIN_RECOMMENDATION_SAMPLES', 12))

# Real-time gas/fire hazard risk scoring defaults. These mirror the firmware's
# active-low flame sensor convention and MQ2 danger threshold while staying tunable.
HAZARD_GAS_WARNING = int(os.getenv('HAZARD_GAS_WARNING', 1800))
HAZARD_GAS_DANGER = int(os.getenv('HAZARD_GAS_DANGER', 3500))
HAZARD_GAS_CRITICAL = int(os.getenv('HAZARD_GAS_CRITICAL', 4095))
HAZARD_FLAME_ACTIVE_VALUE = int(os.getenv('HAZARD_FLAME_ACTIVE_VALUE', 0))
HAZARD_FIRE_RISK_SCORE = int(os.getenv('HAZARD_FIRE_RISK_SCORE', 95))
HAZARD_BUZZER_SCORE = int(os.getenv('HAZARD_BUZZER_SCORE', 55))
HAZARD_SOLENOID_SCORE = int(os.getenv('HAZARD_SOLENOID_SCORE', 75))
HAZARD_NOTIFICATION_SCORE = int(os.getenv('HAZARD_NOTIFICATION_SCORE', 35))

# Browser Web Push configuration. Generate these with:
# python manage.py generate_vapid_keys
WEBPUSH_VAPID_PUBLIC_KEY = os.getenv('WEBPUSH_VAPID_PUBLIC_KEY', '')
WEBPUSH_VAPID_PRIVATE_KEY = os.getenv('WEBPUSH_VAPID_PRIVATE_KEY', '')
WEBPUSH_VAPID_SUBJECT = os.getenv('WEBPUSH_VAPID_SUBJECT', 'mailto:admin@example.com')
