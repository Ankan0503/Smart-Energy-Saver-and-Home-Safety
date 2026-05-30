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
            
            c1 = float(data.get("c1", 0.0))
            c2 = float(data.get("c2", 0.0))
            c3 = float(data.get("c3", 0.0))
            c4 = float(data.get("c4", 0.0))
            
            device = None
            if mac:
                role = "sensor"
                name = "Sensor Node"
                if "c1" in data or "c2" in data or "c3" in data or "c4" in data or mac == "70:4B:CA:27:78:84":
                    role = "relay"
                    name = "ESP32 Relay Node"

                device, created = Device.objects.get_or_create(
                    mac_address=mac,
                    defaults={
                        "name": f"Unassigned {name}",
                        "role": role,
                        "is_paired": False
                    }
                )

                if device.role != role:
                    device.role = role
                    device.name = f"Unassigned {name}"
                
                device.save() # Auto-updates last_seen

                # Auto-create 4 default appliance channels for relay nodes if missing
                if device.role == 'relay':
                    from devices.models import Appliance
                    default_names = ["Living Room Lights", "Smart Charger", "Thermostat", "Media Unit"]
                    default_types = ["Lights", "Appliance", "HVAC", "Samsung TV"]
                    default_consumptions = [45, 1200, 800, 150]
                    for ch in range(1, 5):
                        Appliance.objects.get_or_create(
                            device=device,
                            channel=ch,
                            defaults={
                                "name": default_names[ch - 1],
                                "type": default_types[ch - 1],
                                "nominal_consumption": default_consumptions[ch - 1]
                            }
                        )
            
            # 1. Save the overall/combined device telemetry reading
            TelemetryReading.objects.create(
                device_id=str(device.id) if device else None,
                appliance_id=None,
                gas=gas,
                current=current, # Combined/total current
                pir=pir,
                flame=flame,
                status=status,
                c1=c1,
                c2=c2,
                c3=c3,
                c4=c4
            )

            # 2. Save individual telemetry readings for each appliance on the relay node
            if device and device.role == 'relay':
                from devices.models import Appliance
                appliances = Appliance.objects.filter(device=device)
                channel_currents = {
                    1: c1,
                    2: c2,
                    3: c3,
                    4: c4
                }
                for app in appliances:
                    app_current = channel_currents.get(app.channel, 0.0)
                    TelemetryReading.objects.create(
                        device_id=str(device.id),
                        appliance_id=app.id,
                        gas=gas,
                        current=int(app_current), # Save the individual channel current here
                        pir=pir,
                        flame=flame,
                        status=status,
                        c1=c1,
                        c2=c2,
                        c3=c3,
                        c4=c4
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
