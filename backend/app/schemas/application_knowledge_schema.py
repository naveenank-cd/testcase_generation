from __future__ import annotations

from typing import Any, Literal
from datetime import datetime, timezone
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.automation_schema import DiscoveredElement


class DiscoveredPageInfo(BaseModel):
    url: str
    route_path: str = "/"
    title: str | None = None
    module_name: str | None = None
    element_count: int = 0
    interactive_elements_count: int = 0
    form_count: int = 0
    is_authenticated_page: bool = False
    discovery_timestamp: datetime | None = None


class DiscoveredActionInfo(BaseModel):
    page_url: str
    action_type: Literal["click", "fill", "select", "check", "uncheck", "submit", "navigate"]
    element_name: str
    element_role: str | None = None
    element_tag: str
    verified_locator: str | None = None
    target_url: str | None = None
    input_type: str | None = None
    required: bool = False


class NavigationPathInfo(BaseModel):
    from_url: str
    to_url: str
    via_element_name: str
    verified_locator: str | None = None
    action_type: str = "click"


class DiscoveredFormFieldInfo(BaseModel):
    name: str | None = None
    label: str | None = None
    input_type: str | None = None
    placeholder: str | None = None
    required: bool = False
    verified_locator: str | None = None


class DiscoveredFormInfo(BaseModel):
    page_url: str
    form_id: str | None = None
    form_name: str | None = None
    fields: list[DiscoveredFormFieldInfo] = Field(default_factory=list)
    submit_button_name: str | None = None
    submit_locator: str | None = None


class InteractiveOptionInfo(BaseModel):
    label: str
    value: str | None = None
    locator: str | None = None
    is_default_or_selected: bool = False


class ObservedStateTransition(BaseModel):
    action_type: str
    option_selected: str | None = None
    initial_state_fingerprint: str | None = None
    resulting_state_fingerprint: str | None = None
    url_before: str
    url_after: str
    status: Literal["OBSERVED", "DISCOVERED", "INFERRED", "UNKNOWN", "REQUIRES_FURTHER_EXPLORATION"] = "OBSERVED"
    visible_changes_observed: str | None = None
    newly_visible_elements_count: int = 0
    newly_visible_elements_sample: list[str] = Field(default_factory=list)
    screenshot_path: str | None = None
    error: str | None = None


class InteractiveControlSummary(BaseModel):
    control_id: str
    page_url: str
    control_name: str
    control_type: str
    verified_locator: str | None = None
    options: list[InteractiveOptionInfo] = Field(default_factory=list)
    observed_transitions: list[ObservedStateTransition] = Field(default_factory=list)
    exploration_status: Literal["OBSERVED", "DISCOVERED", "UNKNOWN", "REQUIRES_FURTHER_EXPLORATION"] = "DISCOVERED"


class InteractiveStateObservation(BaseModel):
    observation_id: str
    page_url: str
    control_name: str
    control_type: str
    action_type: str
    option_chosen: str | None = None
    url_before: str
    url_after: str
    initial_state_fingerprint: str
    resulting_state_fingerprint: str
    newly_visible_elements: list[str] = Field(default_factory=list)
    visible_text_delta: str | None = None
    screenshot_path: str | None = None
    status: Literal["OBSERVED", "DISCOVERED", "INFERRED", "UNKNOWN", "REQUIRES_FURTHER_EXPLORATION"] = "OBSERVED"
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApplicationKnowledge(BaseModel):
    """Structured knowledge representing actual discovered information from the deployed application."""
    application_url: str
    crawl_id: str | None = None
    workflow_id: UUID | None = None
    project_id: UUID | None = None
    crawl_status: Literal["crawl_completed", "crawl_incomplete", "crawl_blocked"] = "crawl_completed"
    pages: list[DiscoveredPageInfo] = Field(default_factory=list)
    elements_by_page: dict[str, list[DiscoveredElement]] = Field(default_factory=dict)
    actions: list[DiscoveredActionInfo] = Field(default_factory=list)
    navigation_paths: list[NavigationPathInfo] = Field(default_factory=list)
    forms: list[DiscoveredFormInfo] = Field(default_factory=list)
    interactive_controls: list[InteractiveControlSummary] = Field(default_factory=list)
    interactive_observations: list[InteractiveStateObservation] = Field(default_factory=list)
    verified_locators: dict[str, str] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FlowStep(BaseModel):
    step_number: int
    page_url: str
    page_title: str | None = None
    action: str
    element_name: str | None = None
    verified_locator: str | None = None
    target_page_url: str | None = None
    expected_state_change: str | None = None
    dependencies: list[str] = Field(default_factory=list)


class FlowSequence(BaseModel):
    sequence_id: str
    name: str
    description: str | None = None
    starting_page: str
    destination_page: str | None = None
    steps: list[FlowStep] = Field(default_factory=list)
    identified_module: str | None = None


class FlowTransition(BaseModel):
    from_page: str
    to_page: str
    action: str
    element_name: str
    verified_locator: str | None = None
    conditions: list[str] = Field(default_factory=list)


class ApplicationFlow(BaseModel):
    """Structured application flow representation derived from crawled Application Knowledge."""
    flow_id: str
    application_url: str
    starting_page: str
    sequences: list[FlowSequence] = Field(default_factory=list)
    transitions: list[FlowTransition] = Field(default_factory=list)
    state_graph: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApplicationModuleInfo(BaseModel):
    module_name: str
    page_urls: list[str] = Field(default_factory=list)
    page_titles: list[str] = Field(default_factory=list)
    summary: str | None = None


class ApplicationModel(BaseModel):
    """Unified evidence-backed Application Model combining Knowledge, Flow, Behaviors, and Verified Locators."""
    application_id: str
    application_url: str
    crawl_id: str | None = None
    workflow_id: UUID | None = None
    modules: list[ApplicationModuleInfo] = Field(default_factory=list)
    pages: list[DiscoveredPageInfo] = Field(default_factory=list)
    elements: list[DiscoveredElement] = Field(default_factory=list)
    interactive_controls: list[InteractiveControlSummary] = Field(default_factory=list)
    observations: list[InteractiveStateObservation] = Field(default_factory=list)
    flow: ApplicationFlow | None = None
    navigation_graph: list[NavigationPathInfo] = Field(default_factory=list)
    confirmed_states: list[dict[str, Any]] = Field(default_factory=list)
    unknown_or_unexplored: list[dict[str, Any]] = Field(default_factory=list)
    verified_locators: dict[str, str] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
