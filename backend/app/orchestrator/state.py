import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

class WorkflowState(TypedDict, total=False):
    workflow_id: uuid.UUID
    project_id: uuid.UUID
    source_type: str
    input_payload: dict[str, Any]
    mock_mode: bool
    confidence_threshold: float
    cache_key: str
    cache_hit: bool
    structured_context: dict[str, Any]
    application_knowledge: dict[str, Any] | None
    application_flow: dict[str, Any] | None
    scenarios: list[dict[str, Any]]
    scenario_validation: dict[str, Any]
    scenario_attempt_count: int
    test_cases: list[dict[str, Any]]
    testcase_validation: dict[str, Any]
    testcase_attempt_count: int
    current_stage: str
    status: str
    errors: list[str]
    manual_intervention_reason: str | None
    started_at: datetime
    completed_at: datetime | None
    cancelled: bool

def initial_state(
    workflow_id,
    project_id,
    source_type,
    input_payload,
    mock_mode=False,
    confidence_threshold=0.95,
) -> WorkflowState:
    return {
        "workflow_id": workflow_id,
        "project_id": project_id,
        "source_type": source_type,
        "input_payload": input_payload,
        "mock_mode": mock_mode,
        "confidence_threshold": confidence_threshold,
        "scenario_attempt_count": 0,
        "testcase_attempt_count": 0,
        "scenarios": [],
        "test_cases": [],
        "application_knowledge": input_payload.get("application_knowledge"),
        "application_flow": input_payload.get("application_flow"),
        "current_stage": "pending",
        "status": "pending",
        "errors": [],
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
        "cancelled": False,
    }

