#include <WiFi.h>
#include <esp_now.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <esp_wifi.h>

// ==========================================
// UNIFIED FIRMWARE COMPILATION SWITCH
// ==========================================
// Uncomment ONLY ONE of the lines below before uploading:
// #define DEVICE_TYPE_KITCHEN
#define DEVICE_TYPE_AUTOMATION

// ==========================================
// CONDITIONAL HARDWARE PIN & CONFIG DEFINITIONS
// ==========================================
#ifdef DEVICE_TYPE_KITCHEN
  const char* NODE_ROLE = "sensor";
  const int FLAME_PIN   = 32;  // Digital Input (Flame Sensor)
  const int GAS_PIN     = 35;  // Analog Input (Gas Sensor)
  const int PIR_PIN     = 33;  // Digital Input (PIR Motion Sensor)
  const int BUZZER_PIN  = 25;  // PWM Output (Local Alarm)
  const int GAS_THRESHOLD = 3500;
#endif

#ifdef DEVICE_TYPE_AUTOMATION
  const char* NODE_ROLE = "relay";
  const int RELAY_PINS[4]   = {18, 22, 21, 19}; // Outputs (Relay Channels 1-4)
  const int CURRENT_PINS[4] = {32, 35, 34, 33}; // Analog Inputs (Current Sensors 1-4)

  // Calibrated Electrical Parameters for True RMS Calculation
  const float VREF = 3300.0;       // ESP32 ADC reference voltage in mV (3.3V)
  const float SENSITIVITY = 185.0; // Sensitivity for 5A version = 185mV/A (Use 66 for 30A version)
  const int ADC_RESOLUTION = 4095; // ESP32 12-bit ADC resolution
#endif

const int RESET_PIN   = 0;   // Physical BOOT Button
const int STATUS_LED  = 2;   // Onboard Blue Status LED

// ==========================================
// THRESHOLDS & LOGIC STATES
// ==========================================
bool isPaired = false;

// ==========================================
// MESH CONFIGURATIONS (Stored in NVS)
// ==========================================
Preferences preferences;
String meshId = "";
String meshKey = "";
String deviceName = "";

unsigned long lastBroadcast = 0;
const unsigned long broadcastInterval = 2000; // Telemetry reports every 2 seconds
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

#ifdef DEVICE_TYPE_AUTOMATION
// Function to calculate true RMS AC Current for a specific sensor pin with dynamic auto-calibration
float getACCurrent(int sensorPin) {
  int samples[200];
  int sampleCount = 0;
  unsigned long startTime = millis();
  long sum = 0;
  
  // 1. Sample the AC wave for exactly 20ms (one complete 50Hz cycle)
  while ((millis() - startTime) < 20 && sampleCount < 200) {
    int rawADC = analogRead(sensorPin);
    samples[sampleCount] = rawADC;
    sum += rawADC;
    sampleCount++;
    delayMicroseconds(100); 
  }
  
  if (sampleCount == 0) return 0.0;
  
  // 2. Average raw value is the dynamically calculated DC bias offset
  float avgADC = (float)sum / sampleCount;
  
  // 3. Root-Mean-Square (RMS) deviation around that dynamic offset
  float sqSum = 0.0;
  for (int i = 0; i < sampleCount; i++) {
    float diff = (float)samples[i] - avgADC;
    sqSum += (diff * diff);
  }
  
  float rmsADC = sqrt(sqSum / sampleCount);
  
  // 4. Convert RMS ADC steps to Voltage (mV) and then to Current (Amps)
  float rmsVoltage = (rmsADC / ADC_RESOLUTION) * VREF;
  float currentAmps = (rmsVoltage / SENSITIVITY) * 1.5;
  
  // 5. Noise filter: treat loads under 9W (40mA) as idle/0
  if (currentAmps < 0.04) {
    currentAmps = 0.0;
  }
  
  return currentAmps;
}
#endif

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

    // Process targeted commands matching this device's credentials or emergency broadcasts
    String targetMac = doc["mac"] | "";

    // Handle universal safety trips broadcasted by the Kitchen Node
    #ifdef DEVICE_TYPE_AUTOMATION
    if (action == "TRIP_RELAY") {
        String incomingMeshId = doc["mesh_id"] | "";
        if (isPaired && incomingMeshId == meshId) {
            Serial.println("🚨 EMERGENCY TRIP RECEIVED FROM MESH SENSOR NODE! SHUTTING DOWN ALL SOCKETS!");
            for (int i = 0; i < 4; i++) {
                digitalWrite(RELAY_PINS[i], HIGH); // Pull HIGH to turn relays OFF (Active-LOW)
            }
            return;
        }
    }
    #endif

    // Process standard web interface commands targeted specifically at this node's MAC
    if (targetMac.equalsIgnoreCase(getMacAddress())) {
        if (action == "PAIR") {
            String newMeshId = doc["mesh_id"];
            String newMeshKey = doc["mesh_key"];
            String newName = doc["name"];
            savePairingConfig(newMeshId, newMeshKey, newName, currentChannel);
        } else if (action == "UNPAIR") {
            resetPairing();
        }
        #ifdef DEVICE_TYPE_AUTOMATION
        else if (action == "CONTROL_RELAY") {
            int channel = doc["channel"];
            bool state = doc["state"];
            if (channel >= 1 && channel <= 4) {
                // Multi-channel relays are Active-LOW (LOW = ON, HIGH = OFF)
                digitalWrite(RELAY_PINS[channel - 1], state ? LOW : HIGH);
                Serial.printf("🎯 Relay Channel %d explicitly set over-the-air to: %s\n", channel, state ? "ON" : "OFF");
            }
        }
        #endif
    }
}

void setup() {
    Serial.begin(115200);

    pinMode(RESET_PIN, INPUT_PULLUP);
    pinMode(STATUS_LED, OUTPUT);
    digitalWrite(STATUS_LED, LOW);

    #ifdef DEVICE_TYPE_KITCHEN
    pinMode(FLAME_PIN, INPUT_PULLUP);
    pinMode(GAS_PIN, INPUT);
    pinMode(PIR_PIN, INPUT);
    ledcAttach(BUZZER_PIN, 2000, 8);
    ledcWrite(BUZZER_PIN, 0);
    #endif

    #ifdef DEVICE_TYPE_AUTOMATION
    for (int i = 0; i < 4; i++) {
        pinMode(RELAY_PINS[i], OUTPUT);
        digitalWrite(RELAY_PINS[i], HIGH); // Relays default to OFF (Active-LOW)
        pinMode(CURRENT_PINS[i], INPUT);
    }
    #endif

    // Load configuration from NVS permanent storage
    loadPairingConfig();

    // Start Wi-Fi in Station mode (required for ESP-NOW radio channels)
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();

    // Initialize ESP-NOW Protocol
    if (esp_now_init() != ESP_OK) {
        Serial.println("Error initializing ESP-NOW");
        return;
    }

    esp_now_register_recv_cb(onDataRecv);
    
    // Register structural broadcast peer
    esp_now_peer_info_t peerInfo;
    memset(&peerInfo, 0, sizeof(peerInfo));
    uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
    memcpy(peerInfo.peer_addr, broadcastAddress, 6);
    peerInfo.channel = 0; // Lock to current environment channel
    peerInfo.encrypt = false;
    if (esp_now_add_peer(&peerInfo) != ESP_OK){
        Serial.println("Failed to add broadcast peer");
    }

    Serial.println("ESP-NOW initialized on Sub-Node.");
}

void loop() {
    // Physical hardware reset check (Hold BOOT button for 5 seconds to unpair)
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

    // ==========================================
    // MODE 1: DISCOVERY CONFIGURATION LAYER (Unpaired)
    // ==========================================
    if (!isPaired) {
        // Slow flashing indicator status light
        digitalWrite(STATUS_LED, (millis() / 500) % 2);

        // Resume sweeping channels if the handshake beacon drops for 45 seconds
        if (gatewayFound && (now - lastGatewaySeen > 45000)) {
            gatewayFound = false;
            Serial.println("⚠️ Lost Gateway signal. Resuming channel hopping...");
        }

        if (now - lastBroadcast > 3000) {
            lastBroadcast = now;
            
            if (!gatewayFound) {
                // Sweep across local frequencies (Channels 1 to 13) to find Gateway portal
                currentChannel++;
                if (currentChannel > 13) currentChannel = 1;
                esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
                Serial.println("📡 Switched Wi-Fi channel to: " + String(currentChannel));
            } else {
                Serial.println("📡 Locked on Gateway channel: " + String(currentChannel) + ". Broadcasting ping.");
            }

            // Fire discovery request frames across the mesh channel
            uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
            char discoPayload[128];
            snprintf(discoPayload, sizeof(discoPayload), 
                     "{\"action\":\"DISCOVER\",\"mac\":\"%s\",\"role\":\"%s\"}", 
                     getMacAddress().c_str(), NODE_ROLE);
            
            esp_now_send(broadcastAddress, (uint8_t *) discoPayload, strlen(discoPayload));
        }
        
        #ifdef DEVICE_TYPE_KITCHEN
        ledcWrite(BUZZER_PIN, 0); // Keep buzzer silent while pairing
        #endif
    } 
    // ==========================================
    // MODE 2: ACTIVE SECURE TELEMETRY LAYER (Paired)
    // ==========================================
    else {
        // Maintain solid indicator only if actively catching Gateway heartbeats
        if (now - lastGatewaySeen <= 15000) {
            digitalWrite(STATUS_LED, HIGH);
        } else {
            // Rapid pulse alert pattern indicates tracking sync loss
            digitalWrite(STATUS_LED, (millis() / 200) % 2);
        }

        // Automatic frequency adjustment if the gateway migrates router channels
        static unsigned long lastChannelHop = 0;
        if (now - lastGatewaySeen > 15000) {
            if (now - lastChannelHop > 6000) { 
                lastChannelHop = now;
                currentChannel++;
                if (currentChannel > 13) currentChannel = 1;
                esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
                Serial.println("⚠️ Lost Gateway heartbeat. Searching on channel: " + String(currentChannel));
            }
        }

        // --- KITCHEN EXHAUST LOGIC BLOCK ---
        #ifdef DEVICE_TYPE_KITCHEN
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

        // Fire physical alarm parameters instantly if hazard bounds break
        if (hasEmergency) {
            if (statusText == "FIRE_EMERGENCY") {
                ledcWriteNote(BUZZER_PIN, NOTE_C, 6); // Piercing fire frequency tone
            } else {
                ledcWriteNote(BUZZER_PIN, NOTE_C, 5); // Pulsing gas hazard tone
            }
            
            // Broadcast instantaneous TRIP command to force all relays open safely
            if (!wasEmergency || (now - lastTripSent > 3000)) {
                lastTripSent = now;
                uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
                char tripPayload[250];
                
                snprintf(tripPayload, sizeof(tripPayload),
                         "{\"action\":\"TRIP_RELAY\",\"mac\":\"%s\",\"mesh_id\":\"%s\",\"signature\":\"%s\",\"status\":\"%s\",\"gas\":%d,\"current\":0,\"pir\":%d,\"flame\":%d}",
                         getMacAddress().c_str(), meshId.c_str(), meshKey.c_str(), statusText.c_str(), gasValue, pirState, flameState);
                
                esp_now_send(broadcastAddress, (uint8_t *) tripPayload, strlen(tripPayload));
                Serial.println("🚨 EMERGENCY SHUTDOWN SENT TO ALL RELAYS: " + String(tripPayload));
            }
        } else {
            ledcWrite(BUZZER_PIN, 0); // Clear physical audio buzzer
        }

        // Routine background environment sensor reports
        if (now - lastBroadcast > broadcastInterval) {
            lastBroadcast = now;

            uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
            char telemetryPayload[256];
            snprintf(telemetryPayload, sizeof(telemetryPayload),
                     "{\"action\":\"TELEMETRY\",\"mac\":\"%s\",\"mesh_id\":\"%s\",\"gas\":%d,\"current\":0,\"pir\":%d,\"flame\":%d,\"status\":\"%s\"}",
                     getMacAddress().c_str(), meshId.c_str(), gasValue, pirState, flameState, statusText.c_str());
            
            esp_now_send(broadcastAddress, (uint8_t *) telemetryPayload, strlen(telemetryPayload));
            Serial.println("Sent kitchen environmental telemetry over ESP-NOW");
        }

        wasEmergency = hasEmergency;
        #endif

        // --- AUTOMATION CURRENT TRANSFORMER BLOCK ---
        #ifdef DEVICE_TYPE_AUTOMATION
        if (now - lastBroadcast > broadcastInterval) {
            lastBroadcast = now;

            // Calculate true Root-Mean-Square (RMS) current drawn from each appliance only when broadcasting
            float c1 = getACCurrent(CURRENT_PINS[0]);
            float c2 = getACCurrent(CURRENT_PINS[1]);
            float c3 = getACCurrent(CURRENT_PINS[2]);
            float c4 = getACCurrent(CURRENT_PINS[3]);
            
            float totalCurrentCombined = c1 + c2 + c3 + c4;
            int r1 = digitalRead(RELAY_PINS[0]) == LOW ? 1 : 0;
            int r2 = digitalRead(RELAY_PINS[1]) == LOW ? 1 : 0;
            int r3 = digitalRead(RELAY_PINS[2]) == LOW ? 1 : 0;
            int r4 = digitalRead(RELAY_PINS[3]) == LOW ? 1 : 0;

            uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
            char telemetryPayload[430];
            
            // Package actual calibrated float string telemetry arrays for dashboard processing
            snprintf(telemetryPayload, sizeof(telemetryPayload),
                     "{\"action\":\"TELEMETRY\",\"mac\":\"%s\",\"mesh_id\":\"%s\",\"gas\":0,\"current\":%.3f,\"pir\":1,\"flame\":1,\"status\":\"SAFE\",\"c1\":%.3f,\"c2\":%.3f,\"c3\":%.3f,\"c4\":%.3f,\"r1\":%d,\"r2\":%d,\"r3\":%d,\"r4\":%d}",
                     getMacAddress().c_str(), meshId.c_str(), totalCurrentCombined, c1, c2, c3, c4, r1, r2, r3, r4);
            
            esp_now_send(broadcastAddress, (uint8_t *) telemetryPayload, strlen(telemetryPayload));
            Serial.println("Sent calibrated True-RMS current matrix arrays over ESP-NOW");
        }
        #endif
    }

    delay(10); // Maintain background processor stability
}
