from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from app.config import Settings
from app.knowledge_base import LocalKnowledgeBase


SYSTEM_PROMPT = """你是大学电路实验助教，主要回答 RLC、电路分析和实验操作问题。
请使用简体中文，先给结论，再解释关键原理；有公式时说明符号含义。
回答控制在 180 个汉字左右，不编造实验数据；信息不足时明确说明。"""


@dataclass(frozen=True)
class AnswerResult:
    text: str
    source: str
    error: str | None = None


class LlmAnswerService:
    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        knowledge_base: LocalKnowledgeBase | None = None,
    ) -> None:
        self.settings = settings
        self.knowledge_base = knowledge_base or LocalKnowledgeBase()
        self.enabled = settings.llm_enabled and bool(settings.llm_api_key)
        self.client = client

        if self.enabled and self.client is None:
            self.client = OpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout_seconds,
                max_retries=0,
            )

    def answer(
        self,
        question: str,
        experiment: str = "general",
    ) -> AnswerResult:
        hits = self.knowledge_base.search(question, experiment)
        context = self.knowledge_base.context(hits)

        if not self.enabled:
            if hits:
                return AnswerResult(
                    text=self.knowledge_base.fallback_answer(hits[0]),
                    source="local_knowledge",
                )
            return AnswerResult(
                text=f"云端已收到问题：{question[:180]}",
                source="fallback",
            )

        try:
            completion = self.client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"实验类型：{experiment}\n"
                            f"本地资料（可能尚待教师复核）：\n{context or '无匹配资料'}\n\n"
                            f"学生问题：{question}\n"
                            "若资料不足，请明确说明，不要补造实验数据。"
                        ),
                    },
                ],
            )
            text = completion.choices[0].message.content
            if not text or not text.strip():
                raise ValueError("模型返回了空回答")
            return AnswerResult(text=text.strip()[:220], source="agnes")
        except Exception as exc:
            print(f"大模型调用失败：{type(exc).__name__}: {exc}")
            if hits:
                return AnswerResult(
                    text=self.knowledge_base.fallback_answer(hits[0]),
                    source="local_knowledge",
                    error="llm_unavailable",
                )
            return AnswerResult(
                text=f"大模型暂时不可用，云端已收到问题：{question[:140]}",
                source="fallback",
                error="llm_unavailable",
            )
