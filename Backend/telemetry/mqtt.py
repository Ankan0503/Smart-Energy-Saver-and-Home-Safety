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
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    from .models import TelemetryReading
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
        
        # Save to SQLite/PostgreSQL database
        TelemetryReading.objects.create(
            gas=data.get("gas", 0),
            current=data.get("current", 0),
            flame=data.get("flame", 1),
            status=data.get("status", "SAFE")
        )
        print(f"Saved Telemetry: {data}")
    except Exception as e:
        print(f"Error parsing MQTT message: {e}")

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
