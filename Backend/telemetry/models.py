from django.db import models
from devices.models import Device

class TelemetryReading(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, null=True, blank=True, related_name='readings')
    gas = models.IntegerField()
    current = models.IntegerField()
    flame = models.IntegerField()
    status = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        device_name = self.device.name if self.device else "Legacy Device"
        return f"{device_name} ({self.status}) at {self.timestamp}"
