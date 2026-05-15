from __future__ import annotations

from common.schemas import PRAnalysis
from exercises import exercise_3_escalation as ex3
from conftest import FakeLLMFactory


def test_node_escalate_interrupts_with_questions(monkeypatch, sample_analysis) -> None:
    captured = {}

    def fake_interrupt(payload: dict) -> dict[str, str]:
        captured.update(payload)
        return {"Is there a migration for existing rows?": "Yes, migration follows."}

    monkeypatch.setattr(ex3, "interrupt", fake_interrupt)

    result = ex3.node_escalate({
        "pr_url": "https://github.com/VinUni-AI20k/PR-Demo/pull/2",
        "analysis": sample_analysis,
    })

    assert captured["kind"] == "escalation"
    assert captured["pr_url"].endswith("/pull/2")
    assert captured["confidence"] == sample_analysis.confidence
    assert captured["confidence_reasoning"] == sample_analysis.confidence_reasoning
    assert captured["summary"] == sample_analysis.summary
    assert captured["risk_factors"] == sample_analysis.risk_factors
    assert captured["questions"] == sample_analysis.escalation_questions
    assert result["escalation_answers"] == {
        "Is there a migration for existing rows?": "Yes, migration follows."
    }


def test_node_escalate_uses_fallback_questions(monkeypatch) -> None:
    captured = {}
    low_confidence = PRAnalysis(
        summary="Risky change",
        risk_factors=["auth"],
        confidence=0.40,
        confidence_reasoning="Auth and storage risks are unclear.",
        escalation_questions=[],
    )

    def fake_interrupt(payload: dict) -> dict[str, str]:
        captured.update(payload)
        return {question: "answer" for question in payload["questions"]}

    monkeypatch.setattr(ex3, "interrupt", fake_interrupt)

    ex3.node_escalate({
        "pr_url": "https://github.com/VinUni-AI20k/PR-Demo/pull/2",
        "analysis": low_confidence,
    })

    assert captured["questions"] == [
        "What is the intent of this PR?",
        "Any migration concerns?",
    ]


def test_node_synthesize_uses_reviewer_answers(monkeypatch, sample_analysis) -> None:
    refined = sample_analysis.model_copy(update={
        "summary": "Refined summary",
        "confidence": 0.78,
        "confidence_reasoning": "Reviewer clarified migration behavior.",
    })
    fake_factory = FakeLLMFactory(refined)
    monkeypatch.setattr(ex3, "get_llm", lambda: fake_factory)

    result = ex3.node_synthesize({
        "pr_diff": "diff --git a/auth.py b/auth.py\n+hash_password()",
        "analysis": sample_analysis,
        "escalation_answers": {"Why MD5?": "It should be bcrypt instead."},
    })

    assert result == {"analysis": refined}
    content = fake_factory.structured.calls[0][1]["content"]
    assert "diff --git" in content
    assert "Why MD5?" in content
    assert "bcrypt" in content


def test_build_graph_wires_escalate_to_synthesize(monkeypatch) -> None:
    added_edges = []
    original_add_edge = ex3.StateGraph.add_edge

    def spy_add_edge(self, start_key, end_key):
        added_edges.append((start_key, end_key))
        return original_add_edge(self, start_key, end_key)

    monkeypatch.setattr(ex3.StateGraph, "add_edge", spy_add_edge)

    ex3.build_graph()

    assert ("escalate", "synthesize") in added_edges
    assert ("synthesize", "commit") in added_edges
