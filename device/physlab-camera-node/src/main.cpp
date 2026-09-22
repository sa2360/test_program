#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "esp_camera.h"

#include "camera_pins.h"
#include "secrets.h"

static const char *DEVICE_ID = "camera01";
static const char *CMD_TOPIC = "physlab/camera01/cmd";
static const char *STATUS_TOPIC = "physlab/camera01/status";

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

static String lastRequestId = "";

struct UploadResult {
  bool success;
  int httpStatus;
  String imageId;
  String error;
  uint32_t receivedBytes;
};

static bool initCamera() {
  camera_config_t config = {};

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;

  config.pin_d0 = CAM_PIN_D0;
  config.pin_d1 = CAM_PIN_D1;
  config.pin_d2 = CAM_PIN_D2;
  config.pin_d3 = CAM_PIN_D3;
  config.pin_d4 = CAM_PIN_D4;
  config.pin_d5 = CAM_PIN_D5;
  config.pin_d6 = CAM_PIN_D6;
  config.pin_d7 = CAM_PIN_D7;

  config.pin_xclk = CAM_PIN_XCLK;
  config.pin_pclk = CAM_PIN_PCLK;
  config.pin_vsync = CAM_PIN_VSYNC;
  config.pin_href = CAM_PIN_HREF;

  config.pin_sccb_sda = CAM_PIN_SIOD;
  config.pin_sccb_scl = CAM_PIN_SIOC;
  config.pin_pwdn = CAM_PIN_PWDN;
  config.pin_reset = CAM_PIN_RESET;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 15;

  // 使用第 1 天确认可用的 PSRAM 存放 JPEG 帧缓存。
  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }

  Serial.println("Camera initialized. JPEG frame buffer is in PSRAM.");
  return true;
}

static void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.printf("Connecting to Wi-Fi: %s", WIFI_SSID);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.printf(
      "Wi-Fi connected. IP=%s RSSI=%d dBm\n",
      WiFi.localIP().toString().c_str(),
      WiFi.RSSI()
  );
}

static void publishStatus(
    const char *requestId,
    const char *state,
    const char *imageId,
    uint32_t imageBytes,
    int httpStatus,
    const char *error
) {
  JsonDocument doc;

  doc["schema"] = "physlab.camera.status.v1";
  doc["device_id"] = DEVICE_ID;
  doc["request_id"] = requestId;
  doc["state"] = state;
  doc["image_id"] = imageId;
  doc["bytes"] = imageBytes;
  doc["http_status"] = httpStatus;
  doc["heap"] = ESP.getFreeHeap();
  doc["psram"] = ESP.getFreePsram();

  if (error == nullptr) {
    doc["error"] = nullptr;
  } else {
    doc["error"] = error;
  }

  char payload[768];
  size_t length = serializeJson(doc, payload, sizeof(payload));

  bool published = mqttClient.publish(STATUS_TOPIC, payload, length);

  Serial.printf(
      "Status publish: state=%s result=%s\n",
      state,
      published ? "success" : "failed"
  );

  serializeJson(doc, Serial);
  Serial.println();
}

static UploadResult uploadJpeg(
    uint8_t *jpegData,
    size_t jpegLength,
    const char *requestId
) {
  UploadResult result = {};
  result.success = false;
  result.httpStatus = 0;
  result.receivedBytes = 0;

  HTTPClient http;

  http.setConnectTimeout(5000);
  http.setTimeout(15000);

  if (!http.begin(IMAGE_UPLOAD_URL)) {
    result.error = "http_begin_failed";
    return result;
  }

  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Device-ID", DEVICE_ID);
  http.addHeader("X-Request-ID", requestId);

  int httpStatus = http.POST(jpegData, jpegLength);
  result.httpStatus = httpStatus;

  if (httpStatus != 201) {
    result.error = "http_upload_failed";

    if (httpStatus > 0) {
      String response = http.getString();
      Serial.printf("HTTP response: %s\n", response.c_str());
    } else {
      Serial.printf(
          "HTTP error: %s\n",
          http.errorToString(httpStatus).c_str()
      );
    }

    http.end();
    return result;
  }

  String response = http.getString();
  http.end();

  JsonDocument doc;
  DeserializationError parseError = deserializeJson(doc, response);

  if (parseError) {
    result.error = "invalid_server_json";
    return result;
  }

  const char *imageId = doc["image_id"] | "";
  const char *responseRequestId = doc["request_id"] | "";
  result.receivedBytes = doc["received_bytes"] | 0;

  if (strlen(imageId) == 0) {
    result.error = "missing_image_id";
    return result;
  }

  if (strcmp(responseRequestId, requestId) != 0) {
    result.error = "request_id_mismatch";
    return result;
  }

  if (result.receivedBytes != jpegLength) {
    result.error = "received_bytes_mismatch";
    return result;
  }

  result.success = true;
  result.imageId = imageId;
  return result;
}

static bool isValidJpeg(const camera_fb_t *fb) {
  return fb != nullptr &&
         fb->buf != nullptr &&
         fb->len >= 4 &&
         fb->buf[0] == 0xFF &&
         fb->buf[1] == 0xD8 &&
         fb->buf[fb->len - 2] == 0xFF &&
         fb->buf[fb->len - 1] == 0xD9;
}

static void handleCaptureCommand(const char *requestId) {
  Serial.printf("Handling capture request: %s\n", requestId);

  uint32_t captureStartMs = millis();
  camera_fb_t *fb = esp_camera_fb_get();

  if (fb == nullptr) {
    Serial.println("Capture failed.");
    publishStatus(
        requestId,
        "capture_failed",
        "",
        0,
        0,
        "frame_buffer_null"
    );
    return;
  }

  uint32_t captureMs = millis() - captureStartMs;
  uint32_t imageBytes = fb->len;

  if (!isValidJpeg(fb)) {
    Serial.println("Captured data is not a valid JPEG.");

    publishStatus(
        requestId,
        "capture_failed",
        "",
        imageBytes,
        0,
        "invalid_jpeg"
    );

    esp_camera_fb_return(fb);
    return;
  }

  Serial.printf(
      "Captured: bytes=%u time=%lu ms heap=%u psram=%u\n",
      imageBytes,
      static_cast<unsigned long>(captureMs),
      ESP.getFreeHeap(),
      ESP.getFreePsram()
  );

  // http.POST 读取 fb->buf，因此在上传完成前不可归还 fb。
  UploadResult upload = uploadJpeg(fb->buf, fb->len, requestId);

  // HTTP 已结束，PSRAM 帧缓存现在可以归还。
  esp_camera_fb_return(fb);

  if (!upload.success) {
    Serial.printf(
        "Upload failed: error=%s http=%d\n",
        upload.error.c_str(),
        upload.httpStatus
    );

    publishStatus(
        requestId,
        "upload_failed",
        "",
        imageBytes,
        upload.httpStatus,
        upload.error.c_str()
    );

    return;
  }

  Serial.printf(
      "Upload success: image_id=%s received_bytes=%u\n",
      upload.imageId.c_str(),
      upload.receivedBytes
  );

  publishStatus(
      requestId,
      "uploaded",
      upload.imageId.c_str(),
      imageBytes,
      upload.httpStatus,
      nullptr
  );
}

static void mqttCallback(char *topic, byte *payload, unsigned int length) {
  Serial.printf("MQTT message received. topic=%s length=%u\n", topic, length);

  JsonDocument doc;
  DeserializationError parseError = deserializeJson(doc, payload, length);

  if (parseError) {
    Serial.printf("Invalid JSON: %s\n", parseError.c_str());
    publishStatus("", "command_rejected", "", 0, 0, "invalid_json");
    return;
  }

  const char *schema = doc["schema"] | "";
  const char *requestId = doc["request_id"] | "";
  const char *action = doc["action"] | "";

  if (strcmp(schema, "physlab.camera.cmd.v1") != 0) {
    publishStatus(
        requestId,
        "command_rejected",
        "",
        0,
        0,
        "unsupported_schema"
    );
    return;
  }

  if (strlen(requestId) == 0) {
    publishStatus(
        "",
        "command_rejected",
        "",
        0,
        0,
        "missing_request_id"
    );
    return;
  }

  if (strcmp(action, "capture") != 0) {
    publishStatus(
        requestId,
        "command_rejected",
        "",
        0,
        0,
        "unsupported_action"
    );
    return;
  }

  if (lastRequestId == requestId) {
    Serial.printf("Duplicate request ignored: %s\n", requestId);

    publishStatus(
        requestId,
        "duplicate_ignored",
        "",
        0,
        0,
        nullptr
    );
    return;
  }

  lastRequestId = requestId;
  handleCaptureCommand(requestId);
}

static void connectMqtt() {
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);

  // Return to loop() after each attempt so Wi-Fi recovery can run too.
  if (!mqttClient.connected() && WiFi.status() == WL_CONNECTED) {
    Serial.printf(
        "Connecting MQTT broker %s:%d\n",
        MQTT_HOST,
        MQTT_PORT
    );
    Serial.printf("Local IP=%s RSSI=%d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());

    String clientId = String(DEVICE_ID) + "-" +
                      String(static_cast<uint32_t>(ESP.getEfuseMac()), HEX);

    bool connected;

    if (strlen(MQTT_USER) > 0) {
      connected = mqttClient.connect(
          clientId.c_str(),
          MQTT_USER,
          MQTT_PASSWORD
      );
    } else {
      connected = mqttClient.connect(clientId.c_str());
    }

    if (connected) {
      Serial.println("MQTT connected.");

      bool subscribed = mqttClient.subscribe(CMD_TOPIC, 1);

      Serial.printf(
          "Subscribed to %s: %s\n",
          CMD_TOPIC,
          subscribed ? "success" : "failed"
      );
    } else {
      Serial.printf(
          "MQTT connect failed, state=%d. Retry in 3 seconds.\n",
          mqttClient.state()
      );
      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println("=== PhysLab Camera Node: Day 8 ===");
  // Status messages include UUID request IDs and exceed PubSubClient's 256-byte default.
  if (!mqttClient.setBufferSize(1024)) {
    Serial.println("MQTT buffer allocation failed.");
    delay(3000);
    ESP.restart();
  }

  if (!psramFound()) {
    Serial.println("PSRAM missing. Check Day 1 platformio.ini.");
    while (true) {
      delay(1000);
    }
  }

  Serial.printf(
      "PSRAM size=%u free=%u\n",
      ESP.getPsramSize(),
      ESP.getFreePsram()
  );

  if (!initCamera()) {
    delay(3000);
    ESP.restart();
  }

  connectWifi();
  connectMqtt();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi disconnected. Restarting.");
    delay(1000);
    ESP.restart();
  }

  if (!mqttClient.connected()) {
    connectMqtt();
  }

  mqttClient.loop();
}
