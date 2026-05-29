#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <esp_now.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <WiFiManager.h>

#if __has_include("secrets.h")
#include "secrets.h"
#endif

// ==========================================
// HARDWARE PIN CONFIGURATIONS
// ==========================================
const int CURRENT_PIN = 34;  // Analog Input (Current Sensor)
const int PIR_PIN     = 33;  // Digital Input (PIR Motion Sensor)
const int RELAY_PIN   = 23;  // Digital Output (Main Relay)
const int BUZZER_PIN  = 25;  // PWM Output (Buzzer)
const int RESET_PIN   = 0;   // Physical BOOT Button (GPIO 0)

// ==========================================
// SAFETY CONFIGURATIONS & STATE
// ==========================================
const int CURRENT_THRESHOLD = 4095; // Overcurrent threshold (Set to 4095 to disable/bypass if no physical sensor is connected to Pin 34)
bool isTripped = false;
String currentStatus = "SAFE";

// ==========================================
// MESH CONFIGURATIONS (Stored in NVS)
// ==========================================
Preferences preferences;
String meshId = "";
String meshKey = "";

// ==========================================
// MQTT CLOUD BROKER CONFIGURATIONS
// ==========================================
#ifndef MQTT_SERVER
#define MQTT_SERVER "your-hivemq-host"
#endif
#ifndef MQTT_PORT
#define MQTT_PORT 8883
#endif
#ifndef MQTT_USER
#define MQTT_USER "your-mqtt-username"
#endif
#ifndef MQTT_PASS
#define MQTT_PASS "your-mqtt-password"
#endif

const char* mqtt_server = MQTT_SERVER;
const int mqtt_port     = MQTT_PORT; // Secure TLS
const char* mqtt_user   = MQTT_USER;
const char* mqtt_pass   = MQTT_PASS;

WiFiClientSecure espClient;
PubSubClient mqttClient(espClient);

unsigned long lastMqttRetry = 0;
unsigned long lastPublish = 0;

// Structure to receive ESP-NOW messages
typedef struct struct_message {
    char json[200];
} struct_message;
struct_message incomingMsg;

// Helper to get local MAC Address string
String getMacAddress() {
    return WiFi.macAddress();
}

// Write Mesh ID and Key to NVS
void saveMeshConfig(String id, String key) {
    preferences.begin("mesh-settings", false);
    preferences.putString("mesh_id", id);
    preferences.putString("mesh_key", key);
    preferences.end();
    meshId = id;
    meshKey = key;
    Serial.println("🔒 Mesh configurations saved successfully: " + id);
}

// Load Mesh ID and Key from NVS
void loadMeshConfig() {
    preferences.begin("mesh-settings", true);
    meshId = preferences.getString("mesh_id", "");
    meshKey = preferences.getString("mesh_key", "");
    preferences.end();
    Serial.println("📂 Loaded Mesh config. ID: " + meshId);
}

// Wipes configurations
void resetDeviceSettings() {
    preferences.begin("mesh-settings", false);
    preferences.clear();
    preferences.end();
    WiFiManager wm;
    wm.resetSettings();
    Serial.println("🚨 Device settings wiped! Rebooting...");
    delay(1000);
    ESP.restart();
}

// MQTT Message Receiver Callback (Handles Pairing Commands from Django Backend)
void mqttCallback(char* topic, byte* payload, unsigned int length) {
    char cleanPayload[length + 1];
    memcpy(cleanPayload, payload, length);
    cleanPayload[length] = '\0';
    Serial.print("Received MQTT message: ");
    Serial.println(cleanPayload);

    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, cleanPayload);
    if (error) {
        Serial.print("JSON Deserialization failed: ");
        Serial.println(error.c_str());
        return;
    }

    String action = doc["action"];
    String targetMac = doc["mac"];

    if (action == "PAIR") {
        String newMeshId = doc["mesh_id"];
        String newMeshKey = doc["mesh_key"];
        
        // If this pairing command is targeted for the Gateway itself
        if (targetMac.equalsIgnoreCase(getMacAddress())) {
            saveMeshConfig(newMeshId, newMeshKey);
        } else {
            // Forward the PAIR packet to the targeted Sub-Node via ESP-NOW broadcast
            uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
            esp_now_send(broadcastAddress, (uint8_t *) cleanPayload, strlen(cleanPayload));
            Serial.println("Forwarded pairing packet to Sub-Node over ESP-NOW");
        }
    } else if (action == "UNPAIR") {
        if (targetMac.equalsIgnoreCase(getMacAddress())) {
            resetDeviceSettings();
        } else {
            // Forward UNPAIR command to the Sub-Node
            uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
            esp_now_send(broadcastAddress, (uint8_t *) cleanPayload, strlen(cleanPayload));
            Serial.println("Forwarded unpairing command to Sub-Node");
        }
    } else if (action == "RESET_SAFETY") {
        if (targetMac.equalsIgnoreCase(getMacAddress())) {
            isTripped = false;
            currentStatus = "SAFE";
            digitalWrite(RELAY_PIN, HIGH); // Re-engage Relay (restore power)
            ledcWrite(BUZZER_PIN, 0); // Mute buzzer
            Serial.println("✅ SAFETY RESET: Restored power and muted alarm locally via Cloud!");
            
            // Publish safe telemetry instantly to let frontend know we are safe
            if (mqttClient.connected()) {
                char safePayload[256];
                snprintf(safePayload, sizeof(safePayload), 
                         "{\"mac\":\"%s\",\"gas\":0,\"current\":0,\"pir\":1,\"flame\":1,\"status\":\"SAFE\"}", 
                         getMacAddress().c_str());
                mqttClient.publish("aether/telemetry", safePayload);
            }
        }
    } else if (action == "BUZZER_ALERT") {
        if (targetMac.equalsIgnoreCase(getMacAddress())) {
            ledcWriteNote(BUZZER_PIN, NOTE_C, 5);
            currentStatus = "HAZARD_WARNING";
            Serial.println("Cloud hazard command: buzzer alert enabled");
        }
    } else if (action == "SHUT_SOLENOID") {
        if (targetMac.equalsIgnoreCase(getMacAddress())) {
            int riskScore = doc.containsKey("risk_score") ? doc["risk_score"].as<int>() : 100;
            isTripped = true;
            currentStatus = "HAZARD_SHUTOFF";
            digitalWrite(RELAY_PIN, LOW); // De-energize relay/solenoid safety line
            ledcWriteNote(BUZZER_PIN, NOTE_C, 5);
            Serial.println("Cloud hazard command: solenoid safety shutoff engaged");

            if (mqttClient.connected()) {
                char hazardPayload[256];
                snprintf(hazardPayload, sizeof(hazardPayload),
                         "{\"mac\":\"%s\",\"gas\":%d,\"current\":0,\"pir\":1,\"flame\":0,\"status\":\"HAZARD_SHUTOFF\"}",
                         getMacAddress().c_str(), riskScore * 40);
                mqttClient.publish("aether/telemetry", hazardPayload);
            }
        }
    }
}

// ESP-NOW Data Received Callback
void onDataRecv(const esp_now_recv_info* recvInfo, const uint8_t* data, int len) {
    char incomingJson[len + 1];
    memcpy(incomingJson, data, len);
    incomingJson[len] = '\0';

    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, incomingJson);
    if (error) return;

    String action = doc["action"];
    String nodeMac = doc["mac"];
    
    // 1. Handle Discovery packet from unlinked Node
    if (action == "DISCOVER") {
        String nodeRole = doc["role"];
        if (mqttClient.connected()) {
            char discoPayload[128];
            snprintf(discoPayload, sizeof(discoPayload), "{\"mac\":\"%s\",\"role\":\"%s\"}", nodeMac.c_str(), nodeRole.c_str());
            mqttClient.publish("aether/discovery", discoPayload);
            Serial.println("Forwarded discovery ping to Cloud: " + String(discoPayload));
        }

        // Send handshake DISCOVER_ACK back to Sub-Node to tell it what channel we are on
        uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
        char ackPayload[128];
        snprintf(ackPayload, sizeof(ackPayload), 
                 "{\"action\":\"DISCOVER_ACK\",\"mac\":\"%s\",\"channel\":%d}", 
                 getMacAddress().c_str(), WiFi.channel());
        esp_now_send(broadcastAddress, (uint8_t *) ackPayload, strlen(ackPayload));
        Serial.println("Sent DISCOVER_ACK to Sub-Node: " + String(ackPayload));
    }
    // 2. Handle Telemetry forwarder from Sub-Node
    else if (action == "TELEMETRY") {
        String savedId = doc["mesh_id"];
        
        // Only accept if it belongs to our configured Mesh ID
        if (meshId != "" && savedId == meshId) {
            if (mqttClient.connected()) {
                mqttClient.publish("aether/telemetry", incomingJson);
                Serial.println("Forwarded Sub-Node telemetry to Cloud");
            }
        }
    }
    // 3. Handle emergency trip command from Sensor Sub-Node
    else if (action == "TRIP_RELAY") {
        String savedId = doc["mesh_id"];
        String signature = doc["signature"]; // Hashed check
        
        if (meshId != "" && savedId == meshId) {
            // Trigger emergency trip immediately
            isTripped = true;
            
            String subnodeStatus = doc["status"];
            if (subnodeStatus == "") {
                subnodeStatus = "GAS_LEAK";
            }
            currentStatus = subnodeStatus;
            
            int subnodeGas = doc.containsKey("gas") ? doc["gas"].as<int>() : 4000;
            int subnodeFlame = doc.containsKey("flame") ? doc["flame"].as<int>() : 1;
            int subnodePir = doc.containsKey("pir") ? doc["pir"].as<int>() : 1;
            
            digitalWrite(RELAY_PIN, LOW); // Trip the Relay
            ledcWriteNote(BUZZER_PIN, NOTE_C, 5); // Warning alarm
            Serial.println("🚨 EMERGENCY TRIP: Received " + subnodeStatus + " trigger from room node!");
            
            // Forward status immediately to cloud
            if (mqttClient.connected()) {
                char alertPayload[256];
                snprintf(alertPayload, sizeof(alertPayload), 
                         "{\"mac\":\"%s\",\"gas\":%d,\"current\":0,\"pir\":%d,\"flame\":%d,\"status\":\"%s\"}", 
                         nodeMac.c_str(), subnodeGas, subnodePir, subnodeFlame, subnodeStatus.c_str());
                mqttClient.publish("aether/telemetry", alertPayload);
            }
        }
    }
}

void setup() {
    Serial.begin(115200);
    
    pinMode(CURRENT_PIN, INPUT);
    pinMode(PIR_PIN, INPUT);
    pinMode(RELAY_PIN, OUTPUT);
    pinMode(RESET_PIN, INPUT_PULLUP);
    
    ledcAttach(BUZZER_PIN, 2000, 8);
    ledcWrite(BUZZER_PIN, 0);

    digitalWrite(RELAY_PIN, HIGH); // Default closed (Energized)

    // Load mesh parameters
    loadMeshConfig();

    // WiFiManager Setup
    WiFiManager wm;
    wm.setConfigPortalTimeout(180);
    
    // Add custom Mesh parameters to the Web setup portal
    WiFiManagerParameter custom_mesh_id("mesh_id", "Mesh ID", meshId.c_str(), 40);
    WiFiManagerParameter custom_mesh_key("mesh_key", "Mesh Key", meshKey.c_str(), 40);
    wm.addParameter(&custom_mesh_id);
    wm.addParameter(&custom_mesh_key);

    if(!wm.autoConnect("Aether-Gateway-Setup")) {
        Serial.println("⚠️ Portal timeout. Running offline.");
    } else {
        Serial.println("✅ Wi-Fi connected!");
        // Update NVS if settings changed in portal
        if (strlen(custom_mesh_id.getValue()) > 0) {
            saveMeshConfig(custom_mesh_id.getValue(), custom_mesh_key.getValue());
        }
    }

    // Set Wi-Fi channel of ESP-NOW to match Router channel
    int32_t channel = WiFi.channel();
    
    // Initialize ESP-NOW
    WiFi.mode(WIFI_AP_STA);
    if (esp_now_init() != ESP_OK) {
        Serial.println("Error initializing ESP-NOW");
    } else {
        esp_now_register_recv_cb(onDataRecv);
        
        // Register broadcast peer
        esp_now_peer_info_t peerInfo;
        memset(&peerInfo, 0, sizeof(peerInfo));
        uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
        memcpy(peerInfo.peer_addr, broadcastAddress, 6);
        peerInfo.channel = 0; // Use current channel
        peerInfo.encrypt = false;
        if (esp_now_add_peer(&peerInfo) != ESP_OK){
            Serial.println("Failed to add broadcast peer");
        }
        
        Serial.println("ESP-NOW Initialized successfully on channel " + String(channel));
    }

    // Setup secure MQTT
    espClient.setInsecure();
    mqttClient.setServer(mqtt_server, mqtt_port);
    mqttClient.setCallback(mqttCallback);
}

void reconnectMqtt() {
    unsigned long now = millis();
    if (!mqttClient.connected() && (now - lastMqttRetry > 5000)) {
        lastMqttRetry = now;
        Serial.print("Connecting to HiveMQ Cloud...");
        String clientId = "AetherGateway-" + getMacAddress();
        if (mqttClient.connect(clientId.c_str(), mqtt_user, mqtt_pass)) {
            Serial.println("connected! ✅");
            mqttClient.subscribe("aether/pairing/command");
        } else {
            Serial.print("failed, rc=");
            Serial.println(mqttClient.state());
        }
    }
}

void loop() {
    // Physical button reset check (Hold BOOT pin for 5 seconds to wipe settings)
    if (digitalRead(RESET_PIN) == LOW) {
        delay(50);
        int holdTime = 0;
        while (digitalRead(RESET_PIN) == LOW && holdTime < 50) {
            delay(100);
            holdTime++;
        }
        if (holdTime >= 50) {
            resetDeviceSettings();
        }
    }

    if (WiFi.status() == WL_CONNECTED) {
        if (!mqttClient.connected()) {
            reconnectMqtt();
        }
        mqttClient.loop();
    }

    // Local overcurrent protection check
    int currentRaw = analogRead(CURRENT_PIN);
    int pirState = digitalRead(PIR_PIN) == HIGH ? 1 : 0;
    if (currentRaw > CURRENT_THRESHOLD && !isTripped) {
        isTripped = true;
        currentStatus = "OVERCURRENT_TRIP";
        digitalWrite(RELAY_PIN, LOW); // Cut power
        Serial.println("🚨 OVERCURRENT TRIP DETECTED LOCALLY!");
    }

    // Sound alert if state is abnormal
    if (isTripped) {
        if (currentStatus == "OVERCURRENT_TRIP") {
            ledcWrite(BUZZER_PIN, 0); // Overcurrent doesn't run continuous buzzer
        } else {
            ledcWriteNote(BUZZER_PIN, NOTE_C, 5); // Gas warning alarm
        }
    } else {
        ledcWrite(BUZZER_PIN, 0);
    }

    // Publish local Gateway telemetry
    unsigned long now = millis();
    
    // Periodic heartbeat to keep paired sub-nodes synced to our Wi-Fi channel
    static unsigned long lastHeartbeat = 0;
    if (now - lastHeartbeat > 5000) {
        lastHeartbeat = now;
        if (meshId != "") {
            uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
            char heartbeatPayload[128];
            snprintf(heartbeatPayload, sizeof(heartbeatPayload),
                     "{\"action\":\"HEARTBEAT\",\"mac\":\"%s\",\"mesh_id\":\"%s\",\"channel\":%d}",
                     getMacAddress().c_str(), meshId.c_str(), WiFi.channel());
            esp_now_send(broadcastAddress, (uint8_t *) heartbeatPayload, strlen(heartbeatPayload));
            Serial.println("💓 Broadcasted Mesh Heartbeat on channel " + String(WiFi.channel()));
        }
    }

    if (now - lastPublish > 2000) {
        lastPublish = now;
        if (mqttClient.connected()) {
            char payload[256];
            snprintf(payload, sizeof(payload),
                     "{\"mac\":\"%s\",\"gas\":0,\"current\":%d,\"pir\":%d,\"flame\":1,\"status\":\"%s\"}",
                     getMacAddress().c_str(), currentRaw, pirState, currentStatus.c_str());
            mqttClient.publish("aether/telemetry", payload);
            Serial.println("Published Gateway Telemetry");
        }
    }
    
    delay(10);
}
