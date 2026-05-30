import os
import json
import threading
import paho.mqtt.client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "inventx/telemetry")
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Connected to HiveMQ MQTT Broker successfully! ✅")
        client.subscribe("aether/#")
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    from telemetry.models import TelemetryReading
    from devices.models import Device
    from django.db import close_old_connections
    try:
        close_old_connections()
        payload = msg.payload.decode()
        data = json.loads(payload)
        
        if msg.topic == "aether/discovery":
            mac = data.get("mac")
            role = data.get("role", "sensor")
            if mac:
                # Add or update unlinked device
                device, created = Device.objects.get_or_create(
                    mac_address=mac,
                    defaults={
                        "name": f"Unassigned {role.capitalize()}",
                        "role": role,
                        "is_paired": False
                    }
                )
                device.save() # Auto-updates last_seen
                print(f"Discovered unlinked device: {mac} (Role: {role})")
                
        elif msg.topic == "aether/telemetry":
            mac = data.get("mac")
            gas = data.get("gas", 0)
            current = data.get("current", 0)
            pir = 1 if int(data.get("pir", 1)) else 0
            flame = data.get("flame", 1)
            status = data.get("status", "SAFE")
            
            device = None
            if mac:
                device, created = Device.objects.get_or_create(
                    mac_address=mac,
                    defaults={
                        "name": "Unassigned Sensor Node",
                        "role": "sensor",
                        "is_paired": False
                    }
                )
                device.save() # Auto-updates last_seen
            
            TelemetryReading.objects.create(
                device_id=str(device.id) if device else None,
                gas=gas,
                current=current,
                pir=pir,
                flame=flame,
                status=status
            )
            print(f"Saved Telemetry from {mac or 'legacy'}: {data}")
            
    except Exception as e:
        print(f"Error parsing MQTT message on {msg.topic}: {e}")

def start_mqtt_listener():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    # HiveMQ Cloud (port 8883) requires secure TLS
    if MQTT_PORT == 8883:
        client.tls_set()

    # Authenticate with credentials if provided
    if MQTT_USER and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        # Run loop in a background thread so it doesn't block Django
        mqtt_thread = threading.Thread(target=client.loop_forever, daemon=True)
        mqtt_thread.start()
        print("Started background MQTT listener thread...")
    except Exception as e:
        print(f"Failed to start MQTT Client: {e}")
