#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <Wire.h>
#include <ADS1X15.h>
#include <time.h>

#include "secrets.h"

namespace
{
constexpr char DEVICE_ID[] = "sensor01";
constexpr char FIRMWARE_VERSION[] = "sensor01-fw-0.5.1";
constexpr char ASSISTANT_QUESTION_TOPIC[] = "physlab/assistant/question";
constexpr char ASSISTANT_ANSWER_TOPIC[] = "physlab/assistant/answer";
constexpr char SENSOR_STATUS_TOPIC[] = "physlab/sensor01/status";
constexpr char SENSOR_COMMAND_TOPIC[] = "physlab/sensor01/cmd";
constexpr char SENSOR_DATA_TOPIC[] = "physlab/sensor01/data";
constexpr char VISION_RESULT_TOPIC[] = "physlab/vision/result";
constexpr char CAMERA_COMMAND_TOPIC[] = "physlab/camera01/cmd";
constexpr char CAMERA_STATUS_TOPIC[] = "physlab/camera01/status";
constexpr char ALARM_TOPIC[] = "physlab/alarm";
constexpr uint16_t MQTT_PORT = 1883;
constexpr uint32_t WIFI_RETRY_INTERVAL_MS = 10000;
constexpr uint32_t MQTT_RETRY_INTERVAL_MS = 2000;
constexpr uint32_t STATUS_INTERVAL_MS = 30000;
constexpr uint32_t SAMPLE_INTERVAL_MS = 5000;

// ADS1115 I2C 引脚 (ESP32 默认)
constexpr int ADS_SDA = 21;
constexpr int ADS_SCL = 22;
constexpr uint8_t ADS_ADDR = 0x48;  // ADDR引脚接地时使用默认地址

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
ADS1115 adc(ADS_ADDR);
String serialInput;
uint32_t lastWiFiAttemptMs = 0;
uint32_t lastMqttAttemptMs = 0;
uint32_t lastStatusMs = 0;
uint32_t lastSampleMs = 0;
bool wifiWasConnected = false;
bool ntpConfigured = false;
bool adsInitialized = false;
bool samplePending = false;
uint32_t sampleStartedMs = 0;
String sampleRequestId;
String pendingCaptureId;
uint32_t captureStartedMs = 0;
String visionHistory[8];
uint8_t visionHistoryIndex = 0;

String newRequestId(const char *kind)
{
    return String(DEVICE_ID) + "-" + kind + "-" + String(esp_random(), HEX) + "-" + String(millis());
}

bool initializeAdc()
{
    if (!adc.begin()) return false;
    // Full-scale conversion range is NOT the maximum safe input voltage.
    // Inputs must remain within the ADC supply rails; use a suitable front end.
    adc.setGain(ADS1X15_GAIN_6144MV);
    adc.setMode(ADS1X15_MODE_SINGLE);
    adc.setDataRate(ADS1X15_DATARATE_7);
    return true;
}

bool clockSynced()
{
    return time(nullptr) >= 1700000000;
}

uint64_t unixMs()
{
    const time_t now = time(nullptr);
    if (now < 1700000000)
    {
        return 0;
    }
    return static_cast<uint64_t>(now) * 1000ULL;
}

String buildStatusPayload(bool online, const char *error)
{
    JsonDocument document;
    document["schema"] = "physlab.sensor.status.v1";
    document["device_id"] = DEVICE_ID;
    document["ts"] = unixMs();
    document["online"] = online;
    document["rssi"] = online ? WiFi.RSSI() : -127;
    document["uptime_ms"] = millis();
    document["heap_bytes"] = ESP.getFreeHeap();
    document["fw"] = FIRMWARE_VERSION;
    document["clock_synced"] = clockSynced();
    document["error"] = error ? error : nullptr;
    document["ads_initialized"] = adsInitialized;

    String payload;
    serializeJson(document, payload);
    return payload;
}

void publishStatus()
{
    if (!mqttClient.connected())
    {
        return;
    }

    const String payload = buildStatusPayload(true, nullptr);
    if (mqttClient.publish(SENSOR_STATUS_TOPIC, payload.c_str(), true))
    {
        Serial.printf("Status published: %s\n", payload.c_str());
        lastStatusMs = millis();
    }
    else
    {
        Serial.println("Status publish failed.");
    }
}

void maintainWiFi()
{
    if (strlen(WIFI_SSID) == 0)
    {
        return;
    }

    const bool connected = WiFi.status() == WL_CONNECTED;
    if (connected)
    {
        if (!wifiWasConnected)
        {
            wifiWasConnected = true;
            Serial.println("WiFi connected.");
            Serial.print("ESP32 IP address: ");
            Serial.println(WiFi.localIP());

            if (!ntpConfigured)
            {
                configTime(0, 0, "pool.ntp.org", "time.nist.gov");
                ntpConfigured = true;
                Serial.println("NTP synchronization requested.");
            }
        }
        return;
    }

    if (wifiWasConnected)
    {
        wifiWasConnected = false;
        Serial.println("WiFi disconnected; local processing remains active.");
    }

    const uint32_t now = millis();
    if (now - lastWiFiAttemptMs < WIFI_RETRY_INTERVAL_MS)
    {
        return;
    }

    lastWiFiAttemptMs = now;
    Serial.printf("Connecting to WiFi: %s\n", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void publishAlarm(
    const char *requestId,
    const char *code,
    const char *message,
    const char *level = "warning")
{
    JsonDocument document;
    document["schema"] = "physlab.alarm.v1";
    document["request_id"] = requestId;
    document["source"] = DEVICE_ID;
    document["code"] = code;
    document["level"] = level;
    document["message"] = message;
    document["ts"] = unixMs();

    String payload;
    serializeJson(document, payload);
    if (mqttClient.publish(ALARM_TOPIC, payload.c_str()))
    {
        Serial.printf("Alarm published: %s\n", payload.c_str());
    }
    else
    {
        Serial.println("Alarm publish failed.");
    }
}

void handleAssistantAnswer(JsonDocument &document)
{
    const char *schema = document["schema"] | "";
    const char *requestId = document["request_id"] | "";
    const char *answer = document["answer"] | "";

    if (strcmp(schema, "physlab.assistant.answer.v1") != 0 ||
        strlen(requestId) == 0 ||
        strlen(answer) == 0)
    {
        Serial.println("Rejected assistant answer: protocol_error");
        return;
    }

    Serial.printf("Cloud answer [%s]: %s\n", requestId, answer);
}

void handleVisionResult(JsonDocument &document)
{
    const char *schema = document["schema"] | "";
    const char *requestId = document["request_id"] | "";
    const char *warning = document["warning"] | "";
    const char *message = document["message"] | "";

    const bool jointFormat = strcmp(schema, "physlab.vision.result.v1") == 0;
    if ((!jointFormat && strcmp(schema, "physlab.vision.v1") != 0) ||
        strlen(requestId) == 0 || strlen(requestId) > 96)
    {
        Serial.println("Rejected vision result: missing_request_id or unsupported_schema");
        return;
    }

    if (jointFormat)
    {
        const char *result = document["result"] | "";
        const char *device = document["device_id"] | "";
        const char *suggestion = document["suggestion"] | "";
        if (strcmp(device, "camera01") != 0 || strlen(suggestion) == 0 ||
            (strcmp(result, "ok") != 0 && strcmp(result, "warning") != 0 &&
             strcmp(result, "danger") != 0 && strcmp(result, "unknown") != 0) ||
            !document["warnings"].is<JsonArray>() || document["warnings"].size() > 8)
        {
            Serial.println("Rejected joint vision result: protocol_error");
            return;
        }
        if (strcmp(result, "ok") == 0 && document["warnings"].size() > 0)
        {
            Serial.println("Rejected conflicting normal result with warnings.");
            return;
        }
        for (JsonObject item : document["warnings"].as<JsonArray>())
        {
            const char *level = item["level"] | "";
            const char *code = item["code"] | "";
            const char *description = item["message"] | "";
            if (strlen(code) == 0 || strlen(code) > 64 || strlen(description) == 0 ||
                (strcmp(level, "info") != 0 && strcmp(level, "warning") != 0 && strcmp(level, "danger") != 0) ||
                (strcmp(level, "danger") == 0 && strcmp(result, "danger") != 0))
            {
                Serial.println("Rejected invalid vision warning.");
                return;
            }
        }
        // Keep a bounded fingerprint history: duplicate QoS messages must not repeat alarms.
        // A later manual/model result for the same request is still accepted.
        String serialized;
        serializeJson(document, serialized);
        uint32_t fingerprint = 2166136261UL;
        for (size_t i = 0; i < serialized.length(); ++i)
            fingerprint = (fingerprint ^ static_cast<uint8_t>(serialized[i])) * 16777619UL;
        const String signature = String(requestId) + ":" + String(fingerprint, HEX);
        for (const String &previous : visionHistory)
            if (previous == signature) return;
        visionHistory[visionHistoryIndex++ % 8] = signature;
        if (pendingCaptureId == requestId) pendingCaptureId = "";
        Serial.printf("Vision %s [%s]: %s\n", result, requestId, suggestion);
        Serial.println("Output: serial-only (actuator GPIOs not yet verified).");
        if (strcmp(result, "ok") == 0) return;
        const char *alarmLevel = strcmp(result, "danger") == 0 ? "critical" : "warning";
        if (document["warnings"].size() == 0)
        {
            publishAlarm(requestId, strcmp(result, "unknown") == 0 ? "vision_unknown" : "vision_warning",
                         suggestion, alarmLevel);
        }
        else
        {
            for (JsonObject item : document["warnings"].as<JsonArray>())
                publishAlarm(requestId, item["code"].as<const char *>(),
                             item["message"].as<const char *>(), alarmLevel);
        }
        return;
    }

    if (pendingCaptureId == requestId) pendingCaptureId = "";
    if (strlen(warning) == 0)
    {
        Serial.printf("Vision normal [%s]: %s\n", requestId, message);
        return;
    }

    Serial.printf("Vision warning [%s]: %s - %s\n", requestId, warning, message);
    publishAlarm(requestId, warning, message);
}

void handleCameraStatus(JsonDocument &document)
{
    const char *requestId = document["request_id"] | "";
    const char *schema = document["schema"] | "";
    const char *state = document["state"] | "";
    if (strcmp(schema, "physlab.camera.status.v1") != 0 ||
        strcmp(document["device_id"] | "", "camera01") != 0)
    {
        Serial.println("Rejected camera status: protocol_error");
        return;
    }
    Serial.printf("Camera [%s]: %s, image=%s, HTTP=%d\n", requestId, state,
                  document["image_id"] | "", document["http_status"] | 0);
    if (pendingCaptureId.length() > 0 && pendingCaptureId == requestId &&
        (strcmp(state, "failed") == 0 || strcmp(state, "capture_failed") == 0 ||
         strcmp(state, "upload_failed") == 0 || strcmp(state, "command_rejected") == 0))
    {
        publishAlarm(requestId, "camera_failed", document["error"] | "Camera capture/upload failed.");
        pendingCaptureId = "";
    }
}

void publishCapture()
{
    if (pendingCaptureId.length() > 0)
    {
        Serial.println("A camera request is still pending; wait for result or timeout.");
        return;
    }
    const String requestId = newRequestId("capture");
    JsonDocument command;
    command["schema"] = "physlab.camera.cmd.v1";
    command["request_id"] = requestId;
    command["ts"] = unixMs();
    command["action"] = "capture";
    command["resolution"] = "VGA";
    command["jpeg_quality"] = 15;
    command["timeout_ms"] = 15000;
    String payload;
    serializeJson(command, payload);
    if (mqttClient.publish(CAMERA_COMMAND_TOPIC, payload.c_str(), false))
    {
        pendingCaptureId = requestId;
        captureStartedMs = millis();
        Serial.printf("Camera command sent [%s].\n", requestId.c_str());
    }
    else Serial.println("Camera command publish failed.");
}

void performSampling(const char *requestId = nullptr)
{
    if (!adsInitialized)
    {
        Serial.println("Error: ADS1115 not initialized");
        if (requestId) publishAlarm(requestId, "sensor_read_error", "ADS1115 is not connected.");
        return;
    }
    if (samplePending)
    {
        if (requestId) publishAlarm(requestId, "sensor_busy", "ADS1115 conversion already pending.");
        return;
    }
    sampleRequestId = requestId ? String(requestId) : newRequestId("sample");
    adc.getError();
    adc.requestADC(0);
    samplePending = true;
    sampleStartedMs = millis();
}

void maintainSampling()
{
    if (!samplePending) return;
    if (millis() - sampleStartedMs > 100 || !adc.isConnected())
    {
        samplePending = false;
        adsInitialized = false;
        publishAlarm(sampleRequestId.c_str(), "sensor_read_error", "ADS1115 conversion timeout or I2C disconnected.");
        return;
    }
    if (adc.isBusy()) return;
    samplePending = false;
    const int16_t raw = adc.getValue();
    if (adc.getError() != ADS1X15_OK)
    {
        adsInitialized = false;
        publishAlarm(sampleRequestId.c_str(), "sensor_read_error", "ADS1115 I2C read failed.");
        return;
    }
    float voltage = adc.toVoltage(static_cast<float>(raw));

    JsonDocument document;
    document["schema"] = "physlab.sensor.data.v1";
    document["device_id"] = DEVICE_ID;
    document["ts"] = unixMs();
    document["request_id"] = sampleRequestId;
    document["experiment"] = "rlc_series";
    document["channel"] = "A0";
    document["voltage_v"] = voltage;
    document["temperature_c"] = nullptr;
    document["quality"] = "degraded"; // Raw measurement, not calibrated yet.
    document["raw"] = raw;
    document["calibrated"] = false;
    document["range_v"] = 6.144;

    String payload;
    serializeJson(document, payload);

    if (mqttClient.publish(SENSOR_DATA_TOPIC, payload.c_str()))
    {
        Serial.printf("Sensor data published: %s\n", payload.c_str());
    }
    else
    {
        Serial.println("Sensor data publish failed.");
    }
}

void handleSensorCommand(JsonDocument &document)
{
    const char *schema = document["schema"] | "";
    const char *requestId = document["request_id"] | "";
    const char *action = document["action"] | "";

    if (strcmp(schema, "physlab.sensor.cmd.v1") != 0 ||
        strlen(requestId) == 0 || strlen(requestId) > 96 ||
        strlen(action) == 0)
    {
        Serial.println("Rejected sensor command: protocol_error");
        return;
    }

    if (strcmp(action, "sample_now") == 0)
    {
        performSampling(requestId);
        return;
    }

    publishAlarm(
        requestId,
        "protocol_error",
        "未知命令或参数缺失",
        "warning");
}

void onMqttMessage(char *topic, byte *payload, unsigned int length)
{
    String message;
    message.reserve(length + 1);
    for (unsigned int index = 0; index < length; ++index)
    {
        message += static_cast<char>(payload[index]);
    }

    JsonDocument document;
    const DeserializationError error = deserializeJson(document, message);
    if (error)
    {
        Serial.printf("MQTT JSON rejected on %s: invalid_json (%s)\n", topic, error.c_str());
        return;
    }

    if (strcmp(topic, ASSISTANT_ANSWER_TOPIC) == 0)
    {
        handleAssistantAnswer(document);
    }
    else if (strcmp(topic, VISION_RESULT_TOPIC) == 0)
    {
        handleVisionResult(document);
    }
    else if (strcmp(topic, SENSOR_COMMAND_TOPIC) == 0)
    {
        handleSensorCommand(document);
    }
    else if (strcmp(topic, CAMERA_STATUS_TOPIC) == 0)
    {
        handleCameraStatus(document);
    }
}

void maintainMqtt()
{
    if (WiFi.status() != WL_CONNECTED || mqttClient.connected())
    {
        return;
    }

    const uint32_t now = millis();
    if (now - lastMqttAttemptMs < MQTT_RETRY_INTERVAL_MS)
    {
        return;
    }
    lastMqttAttemptMs = now;

    const uint64_t chipId = ESP.getEfuseMac();
    const String clientId = "sensor01-" + String(static_cast<uint32_t>(chipId), HEX);
    const String offlinePayload = buildStatusPayload(false, "mqtt_disconnected");

    Serial.printf("Connecting to MQTT broker %s:%u...\n", MQTT_HOST, MQTT_PORT);
    if (mqttClient.connect(
            clientId.c_str(),
            SENSOR_STATUS_TOPIC,
            1,
            true,
            offlinePayload.c_str()))
    {
        Serial.println("MQTT connected.");
        mqttClient.subscribe(ASSISTANT_ANSWER_TOPIC, 1);
        mqttClient.subscribe(VISION_RESULT_TOPIC, 1);
        mqttClient.subscribe(SENSOR_COMMAND_TOPIC, 1);
        mqttClient.subscribe(CAMERA_STATUS_TOPIC, 1);
        Serial.printf("Subscribed: %s\n", ASSISTANT_ANSWER_TOPIC);
        Serial.printf("Subscribed: %s\n", VISION_RESULT_TOPIC);
        Serial.printf("Subscribed: %s\n", SENSOR_COMMAND_TOPIC);
        publishStatus();
        Serial.println("Type a question, /capture, or /sample and press Enter:");
        return;
    }

    Serial.printf("MQTT connection failed, state=%d; background retry continues.\n", mqttClient.state());
}

void publishQuestion(const String &question)
{
    JsonDocument document;
    const String requestId = newRequestId("question");

    document["schema"] = "physlab.assistant.question.v1";
    document["device_id"] = DEVICE_ID;
    document["request_id"] = requestId;
    document["experiment"] = "rlc_series";
    document["ts"] = unixMs();
    document["question"] = question;

    String payload;
    serializeJson(document, payload);

    if (mqttClient.publish(ASSISTANT_QUESTION_TOPIC, payload.c_str()))
    {
        Serial.printf("Question published [%s]: %s\n", requestId.c_str(), question.c_str());
    }
    else
    {
        Serial.println("Question publish failed.");
    }
}

void handleSerialInput()
{
    while (Serial.available() > 0)
    {
        const char character = static_cast<char>(Serial.read());
        if (character == '\r')
        {
            continue;
        }

        if (character == '\n')
        {
            serialInput.trim();
            if (serialInput.length() > 0)
            {
                if (serialInput == "/i2c")
                {
                    if (samplePending) Serial.println("Sampling in progress; retry /i2c shortly.");
                    else
                    {
                        Serial.printf("ADS address probe: SDA=%d SCL=%d configured=0x%02X\n", ADS_SDA, ADS_SCL, ADS_ADDR);
                        for (uint8_t address = 0x48; address <= 0x4B; ++address)
                        {
                            Wire.beginTransmission(address);
                            const uint8_t error = Wire.endTransmission();
                            Serial.printf("I2C 0x%02X: %s (code=%u)\n", address, error == 0 ? "ACK" : "NO_ACK", error);
                        }
                        Serial.println("ACK confirms an I2C response only, not the chip model or calibration.");
                    }
                }
                else if (mqttClient.connected())
                {
                    if (serialInput == "/capture") publishCapture();
                    else if (serialInput == "/sample") performSampling();
                    else publishQuestion(serialInput);
                }
                else
                {
                    Serial.println("MQTT is not connected. Please try again later.");
                }
            }
            serialInput = "";
            Serial.println("Type another question and press Enter:");
            continue;
        }

        if (serialInput.length() < 500)
        {
            serialInput += character;
        }
    }
}
} // namespace

void setup()
{
    Serial.begin(115200);
    delay(1000);
    Serial.println();
    Serial.printf("PhysLab sensor node starting: %s\n", FIRMWARE_VERSION);

    // 初始化 I2C 用于 ADS1115
    Wire.begin(ADS_SDA, ADS_SCL);
    Wire.setTimeOut(20);
    Serial.print("I2C initialized on SDA=");
    Serial.print(ADS_SDA);
    Serial.print(", SCL=");
    Serial.println(ADS_SCL);

    // 尝试初始化 ADS1115
    if (initializeAdc())
    {
        adsInitialized = true;
        Serial.println("ADS1115 initialized successfully.");
        Serial.print("Device address: 0x");
        Serial.println(ADS_ADDR, HEX);
    }
    else
    {
        Serial.println("Warning: ADS1115 initialization failed!");
        Serial.println("Please check I2C connections.");
    }

    mqttClient.setServer(MQTT_HOST, MQTT_PORT);
    mqttClient.setCallback(onMqttMessage);
    if (!mqttClient.setBufferSize(16384)) Serial.println("MQTT buffer allocation failed.");
    WiFi.mode(WIFI_STA);

    if (strlen(WIFI_SSID) == 0)
    {
        Serial.println("WiFi credentials are empty. Fill src/secrets.h and upload again.");
        return;
    }

    lastWiFiAttemptMs = millis() - WIFI_RETRY_INTERVAL_MS;
    maintainWiFi();
}

void loop()
{
    handleSerialInput();
    maintainWiFi();
    maintainMqtt();
    maintainSampling();
    if (pendingCaptureId.length() > 0 && millis() - captureStartedMs > 30000)
    {
        publishAlarm(pendingCaptureId.c_str(), "vision_timeout", "Camera/vision response not received within 30 seconds.");
        pendingCaptureId = "";
    }

    if (mqttClient.connected())
    {
        mqttClient.loop();
        
        // 定期检查 ADS1115 状态
        if (!adsInitialized)
        {
            if (millis() - lastSampleMs > 5000)
            {
                lastSampleMs = millis();
                if (initializeAdc())
                {
                    adsInitialized = true;
                    Serial.println("ADS1115 initialized successfully.");
                    publishStatus();
                }
            }
        }
        // 自动采样（每5秒）
        else if (millis() - lastSampleMs >= SAMPLE_INTERVAL_MS)
        {
            lastSampleMs = millis();
            performSampling();
        }
        
        if (millis() - lastStatusMs >= STATUS_INTERVAL_MS)
        {
            publishStatus();
        }
    }

    delay(10);
}
