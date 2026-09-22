from dataclasses import dataclass
import os

from dotenv import load_dotenv


def _read_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    mqtt_host: str
    mqtt_port: int
    device_id: str
    log_level: str
    llm_enabled: bool = False
    llm_api_key: str = ""
    llm_base_url: str = "https://apihub.agnes-ai.com/v1"
    llm_model: str = "agnes-2.0-flash"
    llm_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("AGNES_API_KEY")
            or os.getenv("OPENAI_API_KEY", "")
        )
        return cls(
            mqtt_host=os.getenv("MQTT_HOST", "127.0.0.1"),
            mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
            device_id=os.getenv("DEVICE_ID", "sensor01"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            llm_enabled=_read_bool("LLM_ENABLED", default=bool(api_key)),
            llm_api_key=api_key,
            llm_base_url=(
                os.getenv("LLM_BASE_URL")
                or os.getenv("OPENAI_BASE_URL")
                or "https://apihub.agnes-ai.com/v1"
            ),
            llm_model=os.getenv("LLM_MODEL", "agnes-2.0-flash"),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
        )
