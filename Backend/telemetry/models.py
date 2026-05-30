from django.db import models
from devices.models import Device

class TelemetryReading(models.Model):
<<<<<<< Updated upstream
    device_id = models.CharField(max_length=50, null=True, blank=True, db_column='device_id')
=======
    device_ref = models.ForeignKey(Device, on_delete=models.CASCADE, null=True, blank=True, related_name='readings')
    device_id = models.CharField(max_length=64)
>>>>>>> Stashed changes
    gas = models.IntegerField()
    current = models.FloatField()
    power = models.FloatField(default=0.0)
    pir = models.IntegerField(default=1)
    flame = models.IntegerField()
    status = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)

    @property
    def device(self):
        if not hasattr(self, '_device_cache'):
            from devices.models import Device
            try:
                self._device_cache = Device.objects.get(id=int(self.device_id)) if self.device_id else None
            except (Device.DoesNotExist, ValueError):
                self._device_cache = None
        return self._device_cache

    def __str__(self):
        device_name = self.device_ref.name if self.device_ref else self.device_id
        return f"{device_name} ({self.status}) at {self.timestamp}"


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
