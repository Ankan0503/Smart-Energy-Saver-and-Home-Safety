from django.db import models
from devices.models import Device

class TelemetryReading(models.Model):
    device_id = models.CharField(max_length=50, null=True, blank=True, db_column='device_id')
    gas = models.IntegerField()
    current = models.IntegerField()
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
            from devices.models import Device
            try:
                self._device_cache = Device.objects.get(id=int(self.device_id)) if self.device_id else None
            except (Device.DoesNotExist, ValueError):
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
        device_name = self.device.name if self.device else "Legacy Device"
        appliance_name = f" - {self.appliance.name}" if self.appliance else ""
        return f"{device_name}{appliance_name} ({self.status}) at {self.timestamp}"
