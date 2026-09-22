from dataclasses import dataclass
from pathlib import Path
import re


KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


@dataclass(frozen=True)
class KnowledgeHit:
    title: str
    experiment: str
    review_status: str
    content: str
    score: int


def _field(text: str, name: str, default: str = "") -> str:
    match = re.search(rf"^{re.escape(name)}:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else default


def _terms(text: str) -> set[str]:
    latin = re.findall(r"[a-z0-9_]+", text.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    # Chinese questions often have no spaces; match meaningful substrings too.
    bigrams = [word[index:index + 2] for word in chinese for index in range(len(word) - 1)]
    return set(latin + chinese + bigrams)


class LocalKnowledgeBase:
    def __init__(self, root: Path = KNOWLEDGE_DIR) -> None:
        self.root = root

    def search(
        self,
        question: str,
        experiment: str = "general",
        limit: int = 2,
    ) -> list[KnowledgeHit]:
        query_terms = _terms(question)
        hits: list[KnowledgeHit] = []

        for path in self.root.rglob("*.md"):
            if path.name.lower() == "readme.md":
                continue
            text = path.read_text(encoding="utf-8")
            document_experiment = _field(text, "experiment", "general")
            review_status = _field(text, "review_status", "pending_review")
            for section in re.split(r"(?m)^##\s+", text)[1:]:
                lines = section.strip().splitlines()
                if not lines:
                    continue
                title = lines[0].strip()
                content = "\n".join(lines[1:]).strip()
                haystack = f"{title}\n{content}".lower()
                score = sum(3 for term in query_terms if term.lower() in haystack)
                if score == 0:
                    continue
                if experiment == document_experiment:
                    score += 2
                if score > 0:
                    hits.append(
                        KnowledgeHit(
                            title=title,
                            experiment=document_experiment,
                            review_status=review_status,
                            content=content,
                            score=score,
                        )
                    )

        hits.sort(key=lambda item: (-item.score, item.title))
        return hits[:limit]

    @staticmethod
    def context(hits: list[KnowledgeHit]) -> str:
        if not hits:
            return ""
        return "\n\n".join(
            f"【{hit.title}｜审核状态：{hit.review_status}】\n{hit.content}"
            for hit in hits
        )

    @staticmethod
    def fallback_answer(hit: KnowledgeHit) -> str:
        clean = re.sub(r"^关键词：.*$", "", hit.content, flags=re.MULTILINE).strip()
        prefix = "【资料待教师复核】" if hit.review_status.startswith("pending") else ""
        return prefix + clean[:220 - len(prefix)]
