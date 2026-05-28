from django.apps import AppConfig
import os

class TelemetryConfig(AppConfig):
    name = 'telemetry'

    def ready(self):
        # Only start MQTT listener in the main process, not the reloader thread
        if os.environ.get('RUN_MAIN') == 'true':
            from .mqtt import start_mqtt_listener
            start_mqtt_listener()
