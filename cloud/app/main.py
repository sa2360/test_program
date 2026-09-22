from app.config import Settings
from app.mqtt_client import CloudMqttService


def main() -> None:
    settings = Settings.from_env()
    print("B同学云端服务启动成功")
    print(f"设备编号：{settings.device_id}")
    print(f"MQTT地址：{settings.mqtt_host}:{settings.mqtt_port}")
    if settings.llm_enabled and settings.llm_api_key:
        print(f"大模型：已启用（{settings.llm_model}）")
    else:
        print("大模型：未启用，优先使用本地知识库并保留固定回退")
    try:
        CloudMqttService(settings).run_forever()
    except KeyboardInterrupt:
        print("\n云端服务已安全停止")


if __name__ == "__main__":
    main()
