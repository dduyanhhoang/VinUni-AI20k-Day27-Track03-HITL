from __future__ import annotations

import asyncio

from common.schemas import AuditEntry, risk_level_for
from exercises import exercise_4_audit as ex4
from conftest import FakeLLMFactory


def run(coro):
    return asyncio.run(coro)


def test_audit_writes_thread_and_pr_url(monkeypatch) -> None:
    captured = {}

    async def fake_write_audit_event(*, thread_id: str, pr_url: str, entry: AuditEntry) -> None:
        captured["thread_id"] = thread_id
        captured["pr_url"] = pr_url
        captured["entry"] = entry

    monkeypatch.setattr(ex4, "write_audit_event", fake_write_audit_event)
    entry = AuditEntry(
        agent_id=ex4.AGENT_ID,
        action="analyze",
        confidence=0.65,
        risk_level=risk_level_for(0.65),
        decision="pending",
        reason="reason",
        execution_time_ms=1,
    )

    run(ex4.audit(
        {"thread_id": "thread-1", "pr_url": "https://github.com/o/r/pull/1"},
        entry,
    ))

    assert captured == {
        "thread_id": "thread-1",
        "pr_url": "https://github.com/o/r/pull/1",
        "entry": entry,
    }


def test_node_analyze_audits_llm_output(monkeypatch, sample_analysis) -> None:
    entries = []

    async def fake_audit(state, entry):
        entries.append(entry)

    monkeypatch.setattr(ex4, "audit", fake_audit)
    monkeypatch.setattr(ex4, "get_llm", lambda: FakeLLMFactory(sample_analysis))

    result = run(ex4.node_analyze({
        "thread_id": "thread-1",
        "pr_url": "https://github.com/o/r/pull/1",
        "pr_title": "Demo",
        "pr_diff": "diff",
    }))

    assert result == {"analysis": sample_analysis}
    entry = entries[0]
    assert entry.action == "analyze"
    assert entry.confidence == sample_analysis.confidence
    assert entry.risk_level == risk_level_for(sample_analysis.confidence)
    assert entry.decision == "pending"
    assert entry.reason == sample_analysis.confidence_reasoning


def test_node_route_audits_decision(monkeypatch, sample_analysis) -> None:
    entries = []

    async def fake_audit(state, entry):
        entries.append(entry)

    monkeypatch.setattr(ex4, "audit", fake_audit)

    result = run(ex4.node_route({"analysis": sample_analysis}))

    assert result == {"decision": "human_approval"}
    assert entries[0].action == "route"
    assert entries[0].decision == "human_approval"
    assert entries[0].risk_level == risk_level_for(sample_analysis.confidence)


def test_node_human_approval_audits_before_and_after_resume(monkeypatch, sample_analysis) -> None:
    entries = []

    async def fake_audit(state, entry):
        entries.append(entry)

    def fake_interrupt(payload):
        return {"choice": "edit", "feedback": "Please mention migration."}

    monkeypatch.setenv("GITHUB_USER", "reviewer1")
    monkeypatch.setattr(ex4, "audit", fake_audit)
    monkeypatch.setattr(ex4, "interrupt", fake_interrupt)

    result = run(ex4.node_human_approval({
        "thread_id": "thread-1",
        "pr_url": "https://github.com/o/r/pull/1",
        "analysis": sample_analysis,
        "pr_diff": "diff",
    }))

    assert result == {"human_choice": "edit", "human_feedback": "Please mention migration."}
    assert [entry.decision for entry in entries] == ["pending", "edit"]
    assert entries[0].action == "human_approval"
    assert entries[1].reviewer_id == "reviewer1"
    assert entries[1].reason == "Please mention migration."


def test_node_commit_audits_rejected(monkeypatch, sample_analysis) -> None:
    entries = []

    async def fake_audit(state, entry):
        entries.append(entry)

    monkeypatch.setattr(ex4, "audit", fake_audit)

    result = run(ex4.node_commit({
        "analysis": sample_analysis,
        "human_choice": "reject",
    }))

    assert result == {"final_action": "rejected"}
    assert entries[0].action == "commit"
    assert entries[0].decision == "reject"
    assert entries[0].reason == "rejected"


def test_node_auto_approve_audits_auto(monkeypatch, sample_analysis) -> None:
    entries = []

    async def fake_audit(state, entry):
        entries.append(entry)

    monkeypatch.setattr(ex4, "audit", fake_audit)
    monkeypatch.setattr(ex4, "_post", lambda state: "committed")

    result = run(ex4.node_auto_approve({"analysis": sample_analysis}))

    assert result == {"final_action": "auto_committed"}
    assert entries[0].action == "auto_approve"
    assert entries[0].decision == "auto"


def test_node_escalate_audits_before_and_after(monkeypatch, sample_analysis) -> None:
    entries = []

    async def fake_audit(state, entry):
        entries.append(entry)

    def fake_interrupt(payload):
        return {question: "answer" for question in payload["questions"]}

    monkeypatch.setenv("GITHUB_USER", "reviewer1")
    monkeypatch.setattr(ex4, "audit", fake_audit)
    monkeypatch.setattr(ex4, "interrupt", fake_interrupt)

    result = run(ex4.node_escalate({
        "analysis": sample_analysis,
        "pr_url": "https://github.com/o/r/pull/2",
    }))

    assert result["escalation_answers"] == {
        "Is there a migration for existing rows?": "answer",
    }
    assert [entry.decision for entry in entries] == ["escalate", "pending"]
    assert entries[1].reviewer_id == "reviewer1"


def test_node_synthesize_audits_refined_analysis(monkeypatch, sample_analysis) -> None:
    refined = sample_analysis.model_copy(update={
        "confidence": 0.82,
        "confidence_reasoning": "Reviewer clarified the risk.",
    })
    entries = []

    async def fake_audit(state, entry):
        entries.append(entry)

    monkeypatch.setattr(ex4, "audit", fake_audit)
    monkeypatch.setattr(ex4, "get_llm", lambda: FakeLLMFactory(refined))

    result = run(ex4.node_synthesize({
        "analysis": sample_analysis,
        "pr_diff": "diff",
        "escalation_answers": {"Question?": "Answer."},
    }))

    assert result == {"analysis": refined}
    assert entries[0].action == "synthesize"
    assert entries[0].confidence == 0.82
    assert entries[0].risk_level == risk_level_for(0.82)
