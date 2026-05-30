from django.db import models
from django.contrib.auth.models import User

class Device(models.Model):
    ROLE_CHOICES = [
        ('gateway', 'Central Gateway'),
        ('sensor', 'Sensor Node'),
        ('relay', 'Relay Node'),
    ]
    mac_address = models.CharField(max_length=17, unique=True)
    name = models.CharField(max_length=100, default="Unassigned Device")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='sensor')
    is_paired = models.BooleanField(default=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='devices')
    room = models.ForeignKey('layout.Room', on_delete=models.SET_NULL, null=True, blank=True, related_name='devices')
    last_seen = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        owner_name = self.owner.username if self.owner else "Unassigned"
        return f"{self.name} ({self.mac_address}) | Role: {self.role} | Owner: {owner_name}"
