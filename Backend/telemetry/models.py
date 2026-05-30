from django.db import models
from devices.models import Device

class TelemetryReading(models.Model):
    device_ref = models.ForeignKey(Device, on_delete=models.CASCADE, null=True, blank=True, related_name='readings')
    device_id = models.CharField(max_length=64)
    gas = models.IntegerField()
    current = models.FloatField()
    power = models.FloatField(default=0.0)
    pir = models.IntegerField(default=1)
    flame = models.IntegerField(default=1)
    status = models.CharField(max_length=50, default="SAFE")
    timestamp = models.DateTimeField(auto_now_add=True)
    c1 = models.FloatField(default=0.0)
    c2 = models.FloatField(default=0.0)
    c3 = models.FloatField(default=0.0)
    c4 = models.FloatField(default=0.0)
    appliance_id = models.IntegerField(null=True, blank=True, db_column='appliance_id')

    @property
    def device(self):
        if not hasattr(self, '_device_cache'):
            self._device_cache = self.device_ref
            if self._device_cache is None and self.device_id:
                try:
                    self._device_cache = Device.objects.get(mac_address=self.device_id)
                except Device.DoesNotExist:
                    self._device_cache = None
        return self._device_cache

    @property
    def appliance(self):
        if not hasattr(self, '_appliance_cache'):
            from devices.models import Appliance
            try:
                self._appliance_cache = Appliance.objects.get(id=int(self.appliance_id)) if self.appliance_id else None
            except (Appliance.DoesNotExist, ValueError):
                self._appliance_cache = None
        return self._appliance_cache

    def __str__(self):
        device_name = self.device.name if self.device else (self.device_id or "Legacy Device")
        appliance_name = f" - {self.appliance.name}" if self.appliance else ""
        return f"{device_name}{appliance_name} ({self.status}) at {self.timestamp}"


class ApplianceStatePrediction(models.Model):
    STATE_ACTIVE = 'ACTIVE'
    STATE_IDLE = 'IDLE'
    STATE_PHANTOM_LOAD = 'PHANTOM_LOAD'
    STATE_ABNORMAL = 'ABNORMAL'
    STATE_CHOICES = [
        (STATE_ACTIVE, 'Active'),
        (STATE_IDLE, 'Idle'),
        (STATE_PHANTOM_LOAD, 'Phantom Load'),
        (STATE_ABNORMAL, 'Abnormal'),
    ]

    telemetry = models.OneToOneField(TelemetryReading, on_delete=models.CASCADE, related_name='prediction')
    device_ref = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, related_name='state_predictions')
    device_id = models.CharField(max_length=64, db_index=True)
    predicted_state = models.CharField(max_length=32, choices=STATE_CHOICES, db_index=True)
    confidence_score = models.FloatField(default=0.0)
    action_taken = models.CharField(max_length=128, blank=True, default='')
    reason = models.TextField(blank=True, default='')
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['device_id', '-timestamp']),
            models.Index(fields=['predicted_state', '-timestamp']),
        ]
