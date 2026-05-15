from __future__ import annotations

from common.schemas import AUTO_APPROVE_THRESHOLD, ESCALATE_THRESHOLD, PRAnalysis
from exercises import exercise_1_confidence as ex1
from conftest import FakeLLMFactory, FakePR


def analysis(confidence: float) -> PRAnalysis:
    return PRAnalysis(
        summary="summary",
        confidence=confidence,
        confidence_reasoning="reason",
    )


def test_node_route_auto_approve_at_threshold() -> None:
    result = ex1.node_route({"analysis": analysis(AUTO_APPROVE_THRESHOLD)})
    assert result == {"decision": "auto_approve"}


def test_node_route_escalates_below_threshold() -> None:
    result = ex1.node_route({"analysis": analysis(ESCALATE_THRESHOLD - 0.01)})
    assert result == {"decision": "escalate"}


def test_node_route_human_approval_between_thresholds() -> None:
    result = ex1.node_route({"analysis": analysis(ESCALATE_THRESHOLD)})
    assert result == {"decision": "human_approval"}


def test_node_analyze_uses_structured_pr_analysis(monkeypatch, sample_analysis) -> None:
    fake_factory = FakeLLMFactory(sample_analysis)
    monkeypatch.setattr(ex1, "get_llm", lambda: fake_factory)

    result = ex1.node_analyze({
        "pr_title": "Demo PR",
        "pr_diff": "diff --git a/app.py b/app.py\n+print('hello')",
    })

    assert result == {"analysis": sample_analysis}
    messages = fake_factory.structured.calls[0]
    assert "Demo PR" in messages[1]["content"]
    assert "diff --git" in messages[1]["content"]


def test_build_graph_runs_to_human_approval(monkeypatch, sample_analysis) -> None:
    monkeypatch.setattr(ex1, "fetch_pr", lambda pr_url: FakePR())
    monkeypatch.setattr(ex1, "get_llm", lambda: FakeLLMFactory(sample_analysis))

    app = ex1.build_graph()
    result = app.invoke({"pr_url": "https://github.com/VinUni-AI20k/PR-Demo/pull/1"})

    assert result["decision"] == "human_approval"
    assert result["final_action"] == "pending_human_approval"
