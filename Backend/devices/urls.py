from django.urls import path
from .views import get_user_devices, get_unlinked_devices, register_device, unregister_device, reset_safety, toggle_security_lock

urlpatterns = [
    path('', get_user_devices, name='user_devices'),
    path('unlinked/', get_unlinked_devices, name='unlinked_devices'),
    path('register/', register_device, name='register_device'),
    path('unregister/', unregister_device, name='unregister_device'),
    path('reset-safety/', reset_safety, name='reset_safety'),
    path('toggle-lock/', toggle_security_lock, name='toggle_security_lock'),
]
