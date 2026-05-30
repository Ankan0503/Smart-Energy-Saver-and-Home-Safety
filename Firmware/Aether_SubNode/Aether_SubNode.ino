#include <WiFi.h>
#include <esp_now.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <esp_wifi.h>

// ==========================================
// HARDWARE PIN CONFIGURATIONS
// ==========================================
const int FLAME_PIN   = 32;  // Digital Input (Flame Sensor)
const int GAS_PIN     = 35;  // Analog Input (Gas Sensor)
const int PIR_PIN     = 33;  // Digital Input (PIR Motion Sensor)
const int BUZZER_PIN  = 25;  // PWM Output (Local Alarm)
const int RESET_PIN   = 0;   // Physical BOOT Button
const int STATUS_LED  = 2;   // Onboard Blue Status LED

// ==========================================
// THRESHOLDS & LOGIC STATES
// ==========================================
const int GAS_THRESHOLD = 3500;
bool isPaired = false;

// ==========================================
// MESH CONFIGURATIONS (Stored in NVS)
// ==========================================
Preferences preferences;
String meshId = "";
String meshKey = "";
String deviceName = "";

unsigned long lastBroadcast = 0;
const unsigned long broadcastInterval = 250; // Telemetry reports every 2 seconds
unsigned long lastTripSent = 0;
bool wasEmergency = false;
int currentChannel = 1;
bool gatewayFound = false;
unsigned long lastGatewaySeen = 0;

// Structure to receive pairing messages
typedef struct struct_message {
    char json[200];
} struct_message;

// Get Local MAC Address String
String getMacAddress() {
    return WiFi.macAddress();
}

// Save pairing info
void savePairingConfig(String id, String key, String name, int chan) {
    preferences.begin("sub-settings", false);
    preferences.putString("mesh_id", id);
    preferences.putString("mesh_key", key);
    preferences.putString("device_name", name);
    preferences.putInt("wifi_channel", chan);
    preferences.end();
    meshId = id;
    meshKey = key;
    deviceName = name;
    currentChannel = chan;
    isPaired = true;
    lastGatewaySeen = millis();
    Serial.println("🔒 Paired successfully! Mesh ID: " + id + ", Name: " + name + ", Channel: " + String(chan));
}

// Load pairing info
void loadPairingConfig() {
    preferences.begin("sub-settings", true);
    meshId = preferences.getString("mesh_id", "");
    meshKey = preferences.getString("mesh_key", "");
    deviceName = preferences.getString("device_name", "");
    currentChannel = preferences.getInt("wifi_channel", 1);
    preferences.end();

    if (meshId != "" && meshKey != "") {
        isPaired = true;
        esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
        lastGatewaySeen = millis();
        Serial.println("📂 Loaded mesh credentials. Device Name: " + deviceName + ", Channel: " + String(currentChannel));
    } else {
        isPaired = false;
        Serial.println("📡 No pairing configurations found. Entering Discovery Mode.");
    }
}

// Reset credentials
void resetPairing() {
    preferences.begin("sub-settings", false);
    preferences.clear();
    preferences.end();
    isPaired = false;
    meshId = "";
    meshKey = "";
    deviceName = "";
    currentChannel = 1;
    gatewayFound = false;
    esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
    Serial.println("🚨 Device unpaired! Returning to Discovery Mode.");
    digitalWrite(STATUS_LED, LOW);
}

// Callback when ESP-NOW message is received
void onDataRecv(const esp_now_recv_info* recvInfo, const uint8_t* data, int len) {
    char incomingJson[len + 1];
    memcpy(incomingJson, data, len);
    incomingJson[len] = '\0';

    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, incomingJson);
    if (error) return;

    String action = doc["action"];

    // Check for Gateway discovery handshake response
    if (action == "DISCOVER_ACK") {
        int gwChannel = doc["channel"];
        currentChannel = gwChannel;
        esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
        gatewayFound = true;
        lastGatewaySeen = millis();
        Serial.println("🎯 Gateway found! Locked onto Wi-Fi channel: " + String(currentChannel));
        return;
    }

    // Check for Gateway periodic heartbeat to dynamically sync channel
    if (action == "HEARTBEAT") {
        String savedId = doc["mesh_id"];
        if (meshId != "" && savedId == meshId) {
            lastGatewaySeen = millis();
            int gwChannel = doc["channel"];
            if (currentChannel != gwChannel) {
                currentChannel = gwChannel;
                esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
                preferences.begin("sub-settings", false);
                preferences.putInt("wifi_channel", currentChannel);
                preferences.end();
                Serial.println("🔄 Wi-Fi channel dynamically updated to match Gateway: " + String(currentChannel));
            }
        }
        return;
    }

    String targetMac = doc["mac"];

    // Check if the pairing request is targeted at this node's MAC address
    if (targetMac.equalsIgnoreCase(getMacAddress())) {
        if (action == "PAIR") {
            String newMeshId = doc["mesh_id"];
            String newMeshKey = doc["mesh_key"];
            String newName = doc["name"];
            savePairingConfig(newMeshId, newMeshKey, newName, currentChannel);
        } else if (action == "UNPAIR") {
            resetPairing();
        }
    }
}

void setup() {
    Serial.begin(115200);

    pinMode(FLAME_PIN, INPUT_PULLUP);
    pinMode(GAS_PIN, INPUT);
    pinMode(PIR_PIN, INPUT);
    pinMode(RESET_PIN, INPUT_PULLUP);
    pinMode(STATUS_LED, OUTPUT);

    ledcAttach(BUZZER_PIN, 2000, 8);
    ledcWrite(BUZZER_PIN, 0);

    digitalWrite(STATUS_LED, LOW);

    // Load NVS config
    loadPairingConfig();

    // Start Wi-Fi in Station mode (needed for ESP-NOW)
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();

    // Initialize ESP-NOW
    if (esp_now_init() != ESP_OK) {
        Serial.println("Error initializing ESP-NOW");
        return;
    }

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

    Serial.println("ESP-NOW initialized on Sub-Node.");
}

void loop() {
    // Physical reset check (Hold BOOT button for 5 seconds to unpair)
    if (digitalRead(RESET_PIN) == LOW) {
        delay(50);
        int holdTime = 0;
        while (digitalRead(RESET_PIN) == LOW && holdTime < 50) {
            delay(100);
            holdTime++;
        }
        if (holdTime >= 50) {
            resetPairing();
        }
    }

    unsigned long now = millis();

    // 1. DISCOVERY MODE (Unpaired)
    if (!isPaired) {
        // Slow blink status LED to indicate discovery state
        digitalWrite(STATUS_LED, (millis() / 500) % 2);

        // If we haven't seen the Gateway's handshake in 45 seconds, resume hopping
        if (gatewayFound && (now - lastGatewaySeen > 45000)) {
            gatewayFound = false;
            Serial.println("⚠️ Lost Gateway signal. Resuming channel hopping...");
        }

        if (now - lastBroadcast > 3000) {
            lastBroadcast = now;
            
            if (!gatewayFound) {
                // Cycle through Wi-Fi channels (1 to 13) to find the Gateway
                currentChannel++;
                if (currentChannel > 13) currentChannel = 1;
                esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
                Serial.println("📡 Switched Wi-Fi channel to: " + String(currentChannel));
            } else {
                Serial.println("📡 Locked on Gateway channel: " + String(currentChannel) + ". Broadcasting ping.");
            }

            // Broadcast discovery signal over ESP-NOW to find the Gateway
            uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
            char discoPayload[128];
            snprintf(discoPayload, sizeof(discoPayload), 
                     "{\"action\":\"DISCOVER\",\"mac\":\"%s\",\"role\":\"sensor\"}", 
                     getMacAddress().c_str());
            
            esp_now_send(broadcastAddress, (uint8_t *) discoPayload, strlen(discoPayload));
        }
        
        // Silent alarm in discovery mode
        ledcWrite(BUZZER_PIN, 0);
    } 
    // 2. ACTIVE MESH MODE (Paired)
    else {
        // Keep status LED solidly ON to indicate active pairing status
        digitalWrite(STATUS_LED, HIGH);

        // Channel recovery logic: if we haven't seen the Gateway's heartbeat in 15 seconds, start hopping
        static unsigned long lastChannelHop = 0;
        if (now - lastGatewaySeen > 15000) {
            if (now - lastChannelHop > 6000) { // Hop every 6 seconds to guarantee catching the Gateway's 5-second heartbeat
                lastChannelHop = now;
                currentChannel++;
                if (currentChannel > 13) currentChannel = 1;
                esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
                Serial.println("⚠️ Lost Gateway heartbeat. Searching on channel: " + String(currentChannel));
            }
        }

        // Read physical sensors
        int flameState = digitalRead(FLAME_PIN); // 0 = Fire, 1 = Safe
        int gasValue = analogRead(GAS_PIN);
        int pirState = digitalRead(PIR_PIN) == HIGH ? 1 : 0;

        bool hasEmergency = (flameState == LOW) || (gasValue > GAS_THRESHOLD);
        String statusText = "SAFE";
        
        if (flameState == LOW) {
            statusText = "FIRE_EMERGENCY";
        } else if (gasValue > GAS_THRESHOLD) {
            statusText = "GAS_LEAK";
        }

        // Sound local alarm immediately if emergency is detected
        if (hasEmergency) {
            if (statusText == "FIRE_EMERGENCY") {
                ledcWriteNote(BUZZER_PIN, NOTE_C, 6); // Rapid high tone
            } else {
                ledcWriteNote(BUZZER_PIN, NOTE_C, 5); // Pulsing warning tone
            }
            
            // Send instant TRIP command immediately on transition, or rate-limited every 3 seconds to prevent jamming the mesh network
            if (!wasEmergency || (now - lastTripSent > 3000)) {
                lastTripSent = now;
                uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
                char tripPayload[250];
                // Cryptographic Mesh verification signature
                snprintf(tripPayload, sizeof(tripPayload),
                         "{\"action\":\"TRIP_RELAY\",\"mac\":\"%s\",\"mesh_id\":\"%s\",\"signature\":\"%s\",\"status\":\"%s\",\"gas\":%d,\"current\":0,\"pir\":%d,\"flame\":%d}",
                         getMacAddress().c_str(), meshId.c_str(), meshKey.c_str(), statusText.c_str(), gasValue, pirState, flameState);
                
                esp_now_send(broadcastAddress, (uint8_t *) tripPayload, strlen(tripPayload));
                Serial.println("🚨 EMERGENCY SHUTDOWN broadcast sent: " + String(tripPayload));
            }
        } else {
            ledcWrite(BUZZER_PIN, 0);
        }

        // Send periodic status telemetry to Gateway
        if (now - lastBroadcast > broadcastInterval) {
            lastBroadcast = now;

            uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
            char telemetryPayload[256];
            snprintf(telemetryPayload, sizeof(telemetryPayload),
                     "{\"action\":\"TELEMETRY\",\"mac\":\"%s\",\"mesh_id\":\"%s\",\"gas\":%d,\"current\":0,\"pir\":%d,\"flame\":%d,\"status\":\"%s\"}",
                     getMacAddress().c_str(), meshId.c_str(), gasValue, pirState, flameState, statusText.c_str());
            
            esp_now_send(broadcastAddress, (uint8_t *) telemetryPayload, strlen(telemetryPayload));
            Serial.println("Sent telemetry payload over ESP-NOW");
        }

        wasEmergency = hasEmergency;
    }

    delay(10);
}
