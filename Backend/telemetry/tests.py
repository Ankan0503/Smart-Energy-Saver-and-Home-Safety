from unittest.mock import patch

from django.test import TestCase, override_settings

from devices.models import Device
from telemetry.ingestion import ingest_telemetry_payload
from telemetry.models import ApplianceStatePrediction, TelemetryReading


class TelemetryIngestionTests(TestCase):
    def test_ingestion_stores_float_current_and_power(self):
        reading, prediction = ingest_telemetry_payload({
            'mac': '7C:9E:BD:AA:00:01',
            'gas': 120,
            'current': 0.42,
            'pir': 1,
            'flame': 1,
            'status': 'SAFE',
        })

        self.assertIsInstance(reading.current, float)
        self.assertAlmostEqual(reading.current, 0.42)
        self.assertAlmostEqual(reading.power, 96.6)
        self.assertEqual(reading.device_id, '7C:9E:BD:AA:00:01')
        self.assertEqual(prediction.telemetry_id, reading.id)
        self.assertTrue(ApplianceStatePrediction.objects.filter(telemetry=reading).exists())

    @override_settings(APPLIANCE_IDLE_CUTOFF_SECONDS=0, APPLIANCE_CUTOFF_ENABLED=True)
    @patch('anomaly.ml.appliance_state.mqtt_publish.single')
    def test_idle_unoccupied_prediction_publishes_cutoff(self, publish_single):
        Device.objects.create(
            mac_address='7C:9E:BD:AA:00:02',
            name='Desk Plug',
            role='relay',
            is_paired=True,
        )

        reading, prediction = ingest_telemetry_payload({
            'mac': '7C:9E:BD:AA:00:02',
            'current': 0.22,
            'power': 50.0,
            'pir': 0,
            'gas': 0,
            'flame': 1,
            'status': 'SAFE',
        })

        self.assertEqual(reading.power, 50.0)
        self.assertEqual(prediction.predicted_state, 'IDLE')
        self.assertTrue(prediction.action_taken.startswith('RELAY_OFF'))
        publish_single.assert_called_once()

    def test_prediction_is_one_to_one_with_telemetry(self):
        reading, prediction = ingest_telemetry_payload({
            'mac': '7C:9E:BD:AA:00:03',
            'current': 0.05,
            'power': 8.0,
            'pir': 0,
            'gas': 0,
            'flame': 1,
            'status': 'SAFE',
        })

        self.assertEqual(TelemetryReading.objects.count(), 1)
        self.assertEqual(prediction, reading.prediction)
