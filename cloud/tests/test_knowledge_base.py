import unittest

from app.knowledge_base import LocalKnowledgeBase


class LocalKnowledgeBaseTests(unittest.TestCase):
    def test_rlc_resonance_can_be_retrieved(self) -> None:
        hits = LocalKnowledgeBase().search(
            "RLC 串联谐振的频率怎么算？", "rlc_series"
        )
        self.assertTrue(hits)
        self.assertEqual(hits[0].experiment, "rlc_series")
        self.assertIn("谐振", hits[0].title)

    def test_unrelated_question_has_no_hit(self) -> None:
        hits = LocalKnowledgeBase().search("法国首都是哪里？", "general")
        self.assertEqual(hits, [])

    def test_selected_experiment_does_not_turn_unrelated_question_into_answer(self) -> None:
        self.assertEqual(LocalKnowledgeBase().search("法国首都是哪里？", "rlc_series"), [])

    def test_chinese_question_without_spaces_finds_relevant_topic(self) -> None:
        hits = LocalKnowledgeBase().search("怎样判断电桥是否平衡？", "wheatstone_bridge")
        self.assertTrue(hits)
        self.assertEqual(hits[0].experiment, "wheatstone_bridge")
        self.assertIn("待教师复核", LocalKnowledgeBase().fallback_answer(hits[0]))


if __name__ == "__main__":
    unittest.main()
