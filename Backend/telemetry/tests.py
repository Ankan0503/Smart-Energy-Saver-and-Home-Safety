from unittest.mock import patch

from django.test import TestCase, override_settings

from devices.models import Device
from anomaly.ml.appliance_state import clear_activation_times, clear_appliance_model_cache
from telemetry.ingestion import ingest_telemetry_payload
from telemetry.models import ApplianceStatePrediction, TelemetryReading


class TelemetryIngestionTests(TestCase):
    def setUp(self):
        clear_appliance_model_cache()
        clear_activation_times()

    def tearDown(self):
        clear_appliance_model_cache()
        clear_activation_times()

    @override_settings(APPLIANCE_STATE_MODEL_PATH='missing-test-appliance-state-model.joblib')
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

    @override_settings(
        APPLIANCE_IDLE_CUTOFF_SECONDS=0,
        APPLIANCE_CUTOFF_ENABLED=True,
        APPLIANCE_STATE_MODEL_PATH='missing-test-appliance-state-model.joblib',
        APPLIANCE_IDLE_POWER_THRESHOLD_WATTS=2.0,
        APPLIANCE_IDLE_CURRENT_THRESHOLD_AMPS=0.02,
        APPLIANCE_CUTOFF_CONFIRMATION_READINGS=1,
    )
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
            'c1': 0.0,
            'c2': 0.0,
            'c3': 0.0,
            'c4': 0.0,
            'r1': 1,
            'r2': 1,
            'r3': 1,
            'r4': 1,
            'pir': 0,
            'gas': 0,
            'flame': 1,
            'status': 'SAFE',
        })

        # Global power is computed from the four channel currents.
        self.assertEqual(reading.power, 0.0)
        self.assertEqual(prediction.predicted_state, 'IDLE')
        # Global prediction must NOT trigger cutoff
        self.assertEqual(prediction.action_taken, '')

        # Fetch predictions for individual channels
        app_preds = ApplianceStatePrediction.objects.filter(
            device_id='7C:9E:BD:AA:00:02'
        ).exclude(telemetry__appliance_id=None)

        ch1_pred = app_preds.get(appliance_channel=1)
        self.assertTrue(ch1_pred.action_taken.startswith('RELAY_OFF'))

        ch2_pred = app_preds.get(appliance_channel=2)
        self.assertTrue(ch2_pred.action_taken.startswith('RELAY_OFF'))

        ch3_pred = app_preds.get(appliance_channel=3)
        self.assertTrue(ch3_pred.action_taken.startswith('RELAY_OFF'))

        ch4_pred = app_preds.get(appliance_channel=4)
        self.assertTrue(ch4_pred.action_taken.startswith('RELAY_OFF'))

        # Verify MQTT single publish was called once per relay socket.
        self.assertEqual(publish_single.call_count, 4)

    @override_settings(APPLIANCE_STATE_MODEL_PATH='missing-test-appliance-state-model.joblib')
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

    @override_settings(
        APPLIANCE_IDLE_CUTOFF_SECONDS=0,
        APPLIANCE_CUTOFF_ENABLED=True,
        APPLIANCE_STATE_MODEL_PATH='missing-test-appliance-state-model.joblib',
        APPLIANCE_IDLE_POWER_THRESHOLD_WATTS=2.0,
        APPLIANCE_IDLE_CURRENT_THRESHOLD_AMPS=0.02,
        APPLIANCE_CUTOFF_CONFIRMATION_READINGS=1,
    )
    @patch('anomaly.ml.appliance_state.mqtt_publish.single')
    def test_channel_cutoff_targets_each_idle_socket(self, publish_single):
        device = Device.objects.create(
            mac_address='7C:9E:BD:AA:00:04',
            name='Desk Plug 2',
            role='relay',
            is_paired=True,
        )
        
        # Simulate active telemetry on channels 1 and 2, but idle on channels 3 and 4.
        reading, prediction = ingest_telemetry_payload({
            'mac': '7C:9E:BD:AA:00:04',
            'c1': 0.05,  # Light active (power = 11.5W)
            'c2': 0.05,  # Charger active (power = 11.5W)
            'c3': 0.0,
            'c4': 0.0,
            'r1': 1,
            'r2': 1,
            'r3': 1,
            'r4': 1,
        })

        # Fetch predictions for individual channels
        app_preds = ApplianceStatePrediction.objects.filter(
            device_id='7C:9E:BD:AA:00:04'
        ).exclude(telemetry__appliance_id=None)

        ch1_pred = app_preds.get(appliance_channel=1)
        self.assertEqual(ch1_pred.action_taken, '')

        ch2_pred = app_preds.get(appliance_channel=2)
        self.assertEqual(ch2_pred.action_taken, '')

        ch3_pred = app_preds.get(appliance_channel=3)
        self.assertTrue(ch3_pred.action_taken.startswith('RELAY_OFF'))

        ch4_pred = app_preds.get(appliance_channel=4)
        self.assertTrue(ch4_pred.action_taken.startswith('RELAY_OFF'))

        self.assertEqual(publish_single.call_count, 2)

    @override_settings(
        APPLIANCE_IDLE_CUTOFF_SECONDS=0,
        APPLIANCE_CUTOFF_ENABLED=True,
        APPLIANCE_STATE_MODEL_PATH='missing-test-appliance-state-model.joblib',
        APPLIANCE_PHANTOM_CUTOFF_HITS=3,
        APPLIANCE_PHANTOM_CUTOFF_POWER_WATTS=25.0,
    )
    @patch('anomaly.ml.appliance_state.mqtt_publish.single')
    def test_phantom_load_requires_consecutive_confirmations(self, publish_single):
        Device.objects.create(
            mac_address='7C:9E:BD:AA:00:05',
            name='Charging Strip',
            role='relay',
            is_paired=True,
        )

        for _ in range(2):
            ingest_telemetry_payload({
                'mac': '7C:9E:BD:AA:00:05',
                'c1': 0.015,  # 3.45W at 230V: low standby, not truly off.
                'c2': 0.0,
                'c3': 0.0,
                'c4': 0.0,
                'r1': 1,
                'r2': 0,
                'r3': 0,
                'r4': 0,
            })

        self.assertEqual(publish_single.call_count, 0)

        ingest_telemetry_payload({
            'mac': '7C:9E:BD:AA:00:05',
            'c1': 0.015,
            'c2': 0.0,
            'c3': 0.0,
            'c4': 0.0,
            'r1': 1,
            'r2': 0,
            'r3': 0,
            'r4': 0,
        })

        ch1_pred = ApplianceStatePrediction.objects.filter(
            device_id='7C:9E:BD:AA:00:05',
            appliance_channel=1,
        ).latest('id')
        self.assertEqual(ch1_pred.predicted_state, 'PHANTOM_LOAD')
        self.assertTrue(ch1_pred.action_taken.startswith('RELAY_OFF'))
        self.assertEqual(publish_single.call_count, 1)

    @override_settings(
        APPLIANCE_IDLE_CUTOFF_SECONDS=0,
        APPLIANCE_CUTOFF_ENABLED=True,
        APPLIANCE_STATE_MODEL_PATH='missing-test-appliance-state-model.joblib',
        APPLIANCE_PHANTOM_CUTOFF_HITS=1,
        APPLIANCE_PHANTOM_CUTOFF_POWER_WATTS=25.0,
        APPLIANCE_CUTOFF_CONFIRMATION_READINGS=1,
    )
    @patch('anomaly.ml.appliance_state.mqtt_publish.single')
    def test_phantom_load_above_standby_ceiling_does_not_cutoff(self, publish_single):
        Device.objects.create(
            mac_address='7C:9E:BD:AA:00:06',
            name='Active Charger',
            role='relay',
            is_paired=True,
        )

        ingest_telemetry_payload({
            'mac': '7C:9E:BD:AA:00:06',
            'c1': 0.12,  # 27.6W: above the standby cutoff ceiling.
            'c2': 0.0,
            'c3': 0.0,
            'c4': 0.0,
            'r1': 1,
            'r2': 0,
            'r3': 0,
            'r4': 0,
        })

        ch1_pred = ApplianceStatePrediction.objects.get(
            device_id='7C:9E:BD:AA:00:06',
            appliance_channel=1,
        )
        self.assertEqual(ch1_pred.predicted_state, 'ACTIVE')
        self.assertEqual(ch1_pred.action_taken, '')
        self.assertEqual(publish_single.call_count, 0)
