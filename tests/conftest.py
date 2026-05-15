from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from common.schemas import PRAnalysis, ReviewComment


@dataclass
class FakePR:
    title: str = "Demo PR"
    diff: str = "diff --git a/app.py b/app.py\n+print('hello')\n"
    files_changed: list[str] = field(default_factory=lambda: ["app.py"])
    head_sha: str = "abcdef1234567890"


class FakeStructuredLLM:
    def __init__(self, analysis: PRAnalysis) -> None:
        self.analysis = analysis
        self.calls: list[Any] = []

    def invoke(self, messages: list[dict[str, str]]) -> PRAnalysis:
        self.calls.append(messages)
        return self.analysis

    async def ainvoke(self, messages: list[dict[str, str]]) -> PRAnalysis:
        self.calls.append(messages)
        return self.analysis


class FakeLLMFactory:
    def __init__(self, analysis: PRAnalysis) -> None:
        self.structured = FakeStructuredLLM(analysis)

    def with_structured_output(self, model: type[PRAnalysis]) -> FakeStructuredLLM:
        assert model is PRAnalysis
        return self.structured


@pytest.fixture
def sample_analysis() -> PRAnalysis:
    return PRAnalysis(
        summary="Adds a small field and updates rendering.",
        risk_factors=["schema change"],
        comments=[
            ReviewComment(
                file="app.py",
                line=12,
                severity="suggestion",
                body="Confirm the migration path for existing rows.",
            )
        ],
        confidence=0.65,
        confidence_reasoning="Moderate confidence because migration behavior is unclear.",
        escalation_questions=["Is there a migration for existing rows?"],
    )
