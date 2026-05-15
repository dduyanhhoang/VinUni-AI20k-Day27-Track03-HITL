from __future__ import annotations

import asyncio

from langgraph.types import Command

from common import review_runner


def run(coro):
    return asyncio.run(coro)


def test_classify_session_status_for_approval_interrupt() -> None:
    row = {"latest_action": "human_approval", "latest_decision": "pending", "latest_reason": "Waiting"}

    assert review_runner.classify_session_status(row) == "awaiting_approval"


def test_classify_session_status_for_escalation_interrupt() -> None:
    row = {"latest_action": "escalate", "latest_decision": "escalate", "latest_reason": "Waiting"}

    assert review_runner.classify_session_status(row) == "awaiting_escalation"


def test_classify_session_status_for_terminal_states() -> None:
    assert review_runner.classify_session_status({
        "latest_action": "commit",
        "latest_decision": "approve",
        "latest_reason": "committed",
    }) == "posted"
    assert review_runner.classify_session_status({
        "latest_action": "commit",
        "latest_decision": "reject",
        "latest_reason": "rejected",
    }) == "rejected"
    assert review_runner.classify_session_status({
        "latest_action": "commit",
        "latest_decision": "pending",
        "latest_reason": "commit_failed",
    }) == "failed"
    assert review_runner.classify_session_status({
        "latest_action": "auto_approve",
        "latest_decision": "auto",
        "latest_reason": "committed",
    }) == "posted"


def test_invoke_review_graph_starts_new_thread(monkeypatch) -> None:
    calls = []

    class FakeGraph:
        async def ainvoke(self, value, cfg):
            calls.append((value, cfg))
            return {"final_action": "rejected"}

    class FakeSaver:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def setup(self):
            return None

    monkeypatch.setattr(review_runner.AsyncSqliteSaver, "from_conn_string", lambda path: FakeSaver())
    monkeypatch.setattr(review_runner, "build_graph", lambda cp: FakeGraph())

    result = run(review_runner.invoke_review_graph(
        "https://github.com/o/r/pull/1",
        "thread-1",
    ))

    assert result == {"final_action": "rejected"}
    assert calls == [(
        {"pr_url": "https://github.com/o/r/pull/1", "thread_id": "thread-1"},
        {"configurable": {"thread_id": "thread-1"}},
    )]


def test_invoke_review_graph_resumes_thread(monkeypatch) -> None:
    calls = []

    class FakeGraph:
        async def ainvoke(self, value, cfg):
            calls.append((value, cfg))
            return {"final_action": "committed"}

    class FakeSaver:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def setup(self):
            return None

    monkeypatch.setattr(review_runner.AsyncSqliteSaver, "from_conn_string", lambda path: FakeSaver())
    monkeypatch.setattr(review_runner, "build_graph", lambda cp: FakeGraph())

    result = run(review_runner.invoke_review_graph(
        "https://github.com/o/r/pull/1",
        "thread-1",
        resume_value={"choice": "approve", "feedback": ""},
    ))

    assert result == {"final_action": "committed"}
    assert isinstance(calls[0][0], Command)
    assert calls[0][1] == {"configurable": {"thread_id": "thread-1"}}


def test_list_review_sessions_returns_status_and_worst_risk(monkeypatch) -> None:
    class FakeCursor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def fetchall(self):
            return [
                {
                    "thread_id": "thread-1",
                    "pr_url": "https://github.com/o/r/pull/1",
                    "started": "2026-05-15T01:00:00Z",
                    "last_event": "2026-05-15T01:02:00Z",
                    "worst_risk": "high",
                    "events": 3,
                    "latest_action": "escalate",
                    "latest_decision": "escalate",
                    "latest_reason": "Waiting",
                }
            ]

    class FakeConn:
        def execute(self, query, params):
            assert "CASE risk_level" in query
            assert params == (25,)
            return FakeCursor()

    class FakeDbConn:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(review_runner, "db_conn", lambda: FakeDbConn())

    sessions = run(review_runner.list_review_sessions())

    assert sessions == [{
        "thread_id": "thread-1",
        "pr_url": "https://github.com/o/r/pull/1",
        "started": "2026-05-15T01:00:00Z",
        "last_event": "2026-05-15T01:02:00Z",
        "worst_risk": "high",
        "events": 3,
        "latest_action": "escalate",
        "latest_decision": "escalate",
        "latest_reason": "Waiting",
        "status": "awaiting_escalation",
    }]
