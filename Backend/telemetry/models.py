from django.db import models
from devices.models import Device

class TelemetryReading(models.Model):
    device_id = models.CharField(max_length=50, null=True, blank=True, db_column='device_id')
    gas = models.IntegerField()
    current = models.IntegerField()
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
        device_name = self.device.name if self.device else "Legacy Device"
        return f"{device_name} ({self.status}) at {self.timestamp}"
