from django.db import models

class TelemetryReading(models.Model):
    gas = models.IntegerField()
    current = models.IntegerField()
    flame = models.IntegerField()
    status = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.status} at {self.timestamp}"
