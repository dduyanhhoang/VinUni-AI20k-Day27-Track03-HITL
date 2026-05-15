from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from exercises import exercise_2_hitl as ex2


def test_node_human_approval_interrupts_with_approval_payload(monkeypatch, sample_analysis) -> None:
    captured = {}

    def fake_interrupt(payload: dict) -> dict:
        captured.update(payload)
        return {"choice": "approve", "feedback": "looks good"}

    monkeypatch.setattr(ex2, "interrupt", fake_interrupt)

    result = ex2.node_human_approval({
        "pr_url": "https://github.com/VinUni-AI20k/PR-Demo/pull/1",
        "analysis": sample_analysis,
        "pr_diff": "x" * 2500,
    })

    assert captured["kind"] == "approval_request"
    assert captured["pr_url"].endswith("/pull/1")
    assert captured["confidence"] == sample_analysis.confidence
    assert captured["confidence_reasoning"] == sample_analysis.confidence_reasoning
    assert captured["summary"] == sample_analysis.summary
    assert captured["comments"] == [comment.model_dump() for comment in sample_analysis.comments]
    assert captured["diff_preview"] == "x" * 2000
    assert result == {"human_choice": "approve", "human_feedback": "looks good"}


def test_build_graph_compiles_with_memory_saver(monkeypatch) -> None:
    captured = {}
    original_compile = ex2.StateGraph.compile

    def spy_compile(self, *args, **kwargs):
        captured.update(kwargs)
        return original_compile(self, *args, **kwargs)

    monkeypatch.setattr(ex2.StateGraph, "compile", spy_compile)

    ex2.build_graph()

    assert isinstance(captured["checkpointer"], MemorySaver)
