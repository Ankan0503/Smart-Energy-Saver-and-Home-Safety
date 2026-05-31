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

        # Global power is computed from sum of channel currents (0.0 + 0.0 + 0.0)
        self.assertEqual(reading.power, 0.0)
        self.assertEqual(prediction.predicted_state, 'IDLE')
        # Global prediction must NOT trigger cutoff
        self.assertEqual(prediction.action_taken, '')

        # Fetch predictions for individual channels
        app_preds = ApplianceStatePrediction.objects.filter(
            device_id='7C:9E:BD:AA:00:02'
        ).exclude(telemetry__appliance_id=None)

        # Channel 1 ("Living Room Lights") is exempt
        ch1_pred = app_preds.get(telemetry__appliance__channel=1)
        self.assertEqual(ch1_pred.action_taken, '')

        # Channel 2 ("Smart Charger") is idle and not exempt, should cutoff
        ch2_pred = app_preds.get(telemetry__appliance__channel=2)
        self.assertTrue(ch2_pred.action_taken.startswith('RELAY_OFF'))

        # Channel 4 ("Media Unit") is idle and not exempt, should cutoff
        ch4_pred = app_preds.get(telemetry__appliance__channel=4)
        self.assertTrue(ch4_pred.action_taken.startswith('RELAY_OFF'))

        # Verify MQTT single publish was called exactly twice (for channels 2 and 4)
        self.assertEqual(publish_single.call_count, 2)

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

    @override_settings(APPLIANCE_IDLE_CUTOFF_SECONDS=0, APPLIANCE_CUTOFF_ENABLED=True)
    @patch('anomaly.ml.appliance_state.mqtt_publish.single')
    def test_active_charger_and_lights_are_exempt(self, publish_single):
        device = Device.objects.create(
            mac_address='7C:9E:BD:AA:00:04',
            name='Desk Plug 2',
            role='relay',
            is_paired=True,
        )
        
        # Simulate active telemetry on channels 1 and 2, but idle on channel 4
        reading, prediction = ingest_telemetry_payload({
            'mac': '7C:9E:BD:AA:00:04',
            'c1': 0.05,  # Light active (power = 11.5W)
            'c2': 0.05,  # Charger active (power = 11.5W)
            'c4': 0.0,   # Media Unit idle (power = 0.0W)
        })

        # Fetch predictions for individual channels
        app_preds = ApplianceStatePrediction.objects.filter(
            device_id='7C:9E:BD:AA:00:04'
        ).exclude(telemetry__appliance_id=None)

        # Channel 1 (Light) has c1 = 0.05, power = 11.5W (PHANTOM_LOAD). Exempt because c1 > 0
        ch1_pred = app_preds.get(telemetry__appliance__channel=1)
        self.assertEqual(ch1_pred.action_taken, '')

        # Channel 2 (Charger) has c2 = 0.05, power = 11.5W (PHANTOM_LOAD). Exempt because c2 > 0
        ch2_pred = app_preds.get(telemetry__appliance__channel=2)
        self.assertEqual(ch2_pred.action_taken, '')

        # Channel 4 (Media Unit) has c4 = 0.0, power = 0W (IDLE). Cutoff expected
        ch4_pred = app_preds.get(telemetry__appliance__channel=4)
        self.assertTrue(ch4_pred.action_taken.startswith('RELAY_OFF'))

        # Only channel 4 should have published a cutoff command
        self.assertEqual(publish_single.call_count, 1)
