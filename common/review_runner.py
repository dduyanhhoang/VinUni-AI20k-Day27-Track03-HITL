"""Reusable review-session runner and audit-backed session summaries."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from common.db import db_conn, db_path
from exercises.exercise_4_audit import build_graph


def classify_session_status(row: dict[str, Any]) -> str:
    action = row.get("latest_action")
    decision = row.get("latest_decision")
    reason = row.get("latest_reason") or ""

    if "failed" in reason:
        return "failed"
    if action == "human_approval" and decision == "pending":
        return "awaiting_approval"
    if action == "escalate" and decision == "escalate":
        return "awaiting_escalation"
    if action == "commit" and decision == "reject":
        return "rejected"
    if action in {"commit", "auto_approve"} and decision in {"approve", "auto"}:
        return "posted"
    return "running"


async def invoke_review_graph(
    pr_url: str,
    thread_id: str,
    resume_value: dict | None = None,
) -> dict:
    async with AsyncSqliteSaver.from_conn_string(db_path()) as cp:
        await cp.setup()
        graph = build_graph(cp)
        cfg = {"configurable": {"thread_id": thread_id}}
        if resume_value is None:
            return await graph.ainvoke({"pr_url": pr_url, "thread_id": thread_id}, cfg)
        return await graph.ainvoke(Command(resume=resume_value), cfg)


async def list_review_sessions(limit: int = 25) -> list[dict[str, Any]]:
    async with db_conn() as conn:
        async with conn.execute(
            """
            WITH latest AS (
                SELECT *
                  FROM audit_events
                 WHERE id IN (
                       SELECT MAX(id)
                         FROM audit_events
                        GROUP BY thread_id, pr_url
                 )
            ),
            grouped AS (
                SELECT thread_id,
                       pr_url,
                       MIN(timestamp) AS started,
                       MAX(timestamp) AS last_event,
                       MAX(CASE risk_level
                             WHEN 'high' THEN 3
                             WHEN 'med' THEN 2
                             WHEN 'low' THEN 1
                             ELSE 0
                           END) AS worst_risk_rank,
                       COUNT(*) AS events
                  FROM audit_events
                 GROUP BY thread_id, pr_url
            )
            SELECT grouped.thread_id,
                   grouped.pr_url,
                   grouped.started,
                   grouped.last_event,
                   CASE grouped.worst_risk_rank
                     WHEN 3 THEN 'high'
                     WHEN 2 THEN 'med'
                     WHEN 1 THEN 'low'
                     ELSE 'unknown'
                   END AS worst_risk,
                   grouped.events,
                   latest.action AS latest_action,
                   latest.decision AS latest_decision,
                   latest.reason AS latest_reason
              FROM grouped
              JOIN latest
                ON latest.thread_id = grouped.thread_id
               AND latest.pr_url = grouped.pr_url
             ORDER BY grouped.last_event DESC
             LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()

    sessions = [dict(row) for row in rows]
    for session in sessions:
        session["status"] = classify_session_status(session)
    return sessions
