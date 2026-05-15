from __future__ import annotations

import importlib


def load_app():
    return importlib.import_module("app")


def test_run_graph_invokes_new_thread(monkeypatch) -> None:
    app_module = load_app()
    calls = []

    async def fake_invoke(pr_url, thread_id, resume_value=None):
        calls.append((pr_url, thread_id, resume_value))
        return {"final_action": "rejected"}

    monkeypatch.setattr(app_module, "invoke_review_graph", fake_invoke)

    result = app_module.asyncio.run(
        app_module.run_graph("https://github.com/o/r/pull/1", "thread-1")
    )

    assert result == {"final_action": "rejected"}
    assert calls == [("https://github.com/o/r/pull/1", "thread-1", None)]


def test_run_graph_resumes_existing_thread(monkeypatch) -> None:
    app_module = load_app()
    calls = []

    async def fake_invoke(pr_url, thread_id, resume_value=None):
        calls.append((pr_url, thread_id, resume_value))
        return {"final_action": "committed"}

    monkeypatch.setattr(app_module, "invoke_review_graph", fake_invoke)

    result = app_module.asyncio.run(app_module.run_graph(
        "https://github.com/o/r/pull/1",
        "thread-1",
        resume_value={"choice": "approve", "feedback": ""},
    ))

    assert result == {"final_action": "committed"}
    assert calls == [(
        "https://github.com/o/r/pull/1",
        "thread-1",
        {"choice": "approve", "feedback": ""},
    )]


def test_group_sessions_by_status() -> None:
    app_module = load_app()

    grouped = app_module.group_sessions_by_status([
        {"thread_id": "1", "status": "awaiting_approval"},
        {"thread_id": "2", "status": "posted"},
        {"thread_id": "3", "status": "awaiting_approval"},
        {"thread_id": "4", "status": "failed"},
    ])

    assert [session["thread_id"] for session in grouped["awaiting_approval"]] == ["1", "3"]
    assert [session["thread_id"] for session in grouped["posted"]] == ["2"]
    assert [session["thread_id"] for session in grouped["failed"]] == ["4"]


def test_render_approval_card_returns_approve(monkeypatch, sample_analysis) -> None:
    app_module = load_app()

    monkeypatch.setattr(app_module.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module.st, "text_input", lambda *args, **kwargs: "ship it")

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    class FakeColumn:
        def __init__(self, clicked: bool) -> None:
            self.clicked = clicked

        def button(self, *args, **kwargs) -> bool:
            return self.clicked

    monkeypatch.setattr(app_module.st, "expander", lambda *args, **kwargs: FakeExpander())
    monkeypatch.setattr(app_module.st, "code", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module.st, "columns", lambda count: [
        FakeColumn(True),
        FakeColumn(False),
        FakeColumn(False),
    ])

    result = app_module.render_approval_card({
        "confidence": sample_analysis.confidence,
        "confidence_reasoning": sample_analysis.confidence_reasoning,
        "summary": sample_analysis.summary,
        "comments": [comment.model_dump() for comment in sample_analysis.comments],
        "diff_preview": "diff",
    })

    assert result == {"choice": "approve", "feedback": "ship it"}


def test_render_escalation_card_returns_answers(monkeypatch) -> None:
    app_module = load_app()

    monkeypatch.setattr(app_module.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module.st, "error", lambda *args, **kwargs: None)

    class FakeForm:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    answers = iter(["Use bcrypt.", "Add migration."])
    monkeypatch.setattr(app_module.st, "form", lambda *args, **kwargs: FakeForm())
    monkeypatch.setattr(app_module.st, "text_input", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(app_module.st, "form_submit_button", lambda *args, **kwargs: True)

    result = app_module.render_escalation_card({
        "confidence": 0.40,
        "confidence_reasoning": "Security-sensitive change.",
        "summary": "Adds auth.",
        "risk_factors": ["MD5", "plaintext token"],
        "questions": ["Why MD5?", "Where is the migration?"],
    })

    assert result == {
        "Why MD5?": "Use bcrypt.",
        "Where is the migration?": "Add migration.",
    }
