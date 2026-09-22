import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.config import Settings
from app.llm_client import AnswerResult, LlmAnswerService
from app.mqtt_client import make_answer


class SettingsTests(unittest.TestCase):
    def test_default_settings_are_available(self) -> None:
        settings = Settings.from_env()
        self.assertTrue(settings.mqtt_host)
        self.assertGreater(settings.mqtt_port, 0)
        self.assertTrue(settings.device_id)

    def test_agnes_key_is_supported(self) -> None:
        with patch.dict(
            "os.environ",
            {"LLM_API_KEY": "", "AGNES_API_KEY": "agnes-test-key"},
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.llm_api_key, "agnes-test-key")

    def test_answer_keeps_request_id(self) -> None:
        payload = {
            "schema": "physlab.assistant.question.v1",
            "device_id": "sensor01",
            "request_id": "test-001",
            "experiment": "rlc_series",
            "ts": 1,
            "question": "测试问题",
        }
        answer = make_answer(
            payload,
            AnswerResult("电感会阻碍电流的变化。", "agnes"),
        )
        self.assertEqual(answer["request_id"], "test-001")
        self.assertEqual(answer["answer"], "电感会阻碍电流的变化。")

    def test_disabled_llm_uses_safe_fallback(self) -> None:
        settings = Settings("127.0.0.1", 1883, "esp32_01", "INFO")
        answer = LlmAnswerService(settings).answer("项目外的问题是什么？")
        self.assertIn("项目外的问题", answer.text)
        self.assertEqual(answer.source, "fallback")

    def test_disabled_llm_can_use_local_knowledge(self) -> None:
        settings = Settings("127.0.0.1", 1883, "sensor01", "INFO")
        answer = LlmAnswerService(settings).answer(
            "RLC 串联谐振是什么？", "rlc_series"
        )
        self.assertIn("谐振", answer.text)
        self.assertEqual(answer.source, "local_knowledge")

    def test_enabled_llm_uses_compatible_chat_api(self) -> None:
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="电感用于储存磁场能量。")
                )
            ]
        )

        class FakeCompletions:
            def create(self, **kwargs):
                self.arguments = kwargs
                return response

        completions = FakeCompletions()
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )
        settings = Settings(
            "127.0.0.1",
            1883,
            "esp32_01",
            "INFO",
            llm_enabled=True,
            llm_api_key="test-key",
            llm_model="test-model",
        )

        answer = LlmAnswerService(settings, client=fake_client).answer(
            "什么是电感？", "rlc_series"
        )

        self.assertEqual(answer.text, "电感用于储存磁场能量。")
        self.assertEqual(answer.source, "agnes")
        self.assertEqual(completions.arguments["model"], "test-model")
        self.assertIn("什么是电感", completions.arguments["messages"][1]["content"])
        self.assertIn("本地资料", completions.arguments["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
