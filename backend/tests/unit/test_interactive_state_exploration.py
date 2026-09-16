import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.automation_service import is_safe_action_text
from app.services.application_knowledge_service import application_knowledge_service
from app.schemas.application_knowledge_schema import (
    ApplicationModel,
    InteractiveControlSummary,
    InteractiveOptionInfo,
    InteractiveStateObservation,
    ObservedStateTransition,
)


def test_safe_action_filter_blocks_destructive_keywords():
    assert is_safe_action_text("Filter by Status") is True
    assert is_safe_action_text("All Appointments") is True
    assert is_safe_action_text("Next Page") is True
    assert is_safe_action_text("Sort by Date") is True
    assert is_safe_action_text("Select Role") is True

    # Destructive keywords must be rejected
    assert is_safe_action_text("Delete Account") is False
    assert is_safe_action_text("Remove User") is False
    assert is_safe_action_text("Logout") is False
    assert is_safe_action_text("Sign Out") is False
    assert is_safe_action_text("Cancel Subscription") is False
    assert is_safe_action_text("Purge Records") is False
    assert is_safe_action_text("Clear Database") is False


def test_interactive_state_ingestion_and_flow_derivation():
    crawl_data = {
        "crawl_id": "crawl-interactive-test-01",
        "application_url": "https://enterprise.example.com",
        "crawl_status": "crawl_completed",
        "page_title": "Enterprise Dashboard",
        "crawl_report": {
            "pages_completed": 1,
            "page_inventory": [
                {
                    "url": "https://enterprise.example.com",
                    "title": "Enterprise Dashboard",
                    "elements": [],
                }
            ],
            "interactive_controls": [
                {
                    "control_id": "ctrl_filter_status",
                    "page_url": "https://enterprise.example.com",
                    "control_name": "Status Filter",
                    "control_type": "select_dropdown",
                    "verified_locator": "select#status-filter",
                    "options": [
                        {"label": "All", "value": "all", "is_default_or_selected": True},
                        {"label": "Active", "value": "active", "is_default_or_selected": False},
                        {"label": "Pending", "value": "pending", "is_default_or_selected": False},
                    ],
                    "observed_transitions": [
                        {
                            "action_type": "select",
                            "option_selected": "Active",
                            "initial_state_fingerprint": "fp_init_01",
                            "resulting_state_fingerprint": "fp_res_active",
                            "url_before": "https://enterprise.example.com",
                            "url_after": "https://enterprise.example.com",
                            "status": "OBSERVED",
                            "visible_changes_observed": "Table refreshed to display 14 active records.",
                            "newly_visible_elements_count": 14,
                            "newly_visible_elements_sample": ["Record Active #1", "Record Active #2"],
                        }
                    ],
                    "exploration_status": "OBSERVED",
                }
            ],
            "interactive_observations": [
                {
                    "observation_id": "obs-1001",
                    "page_url": "https://enterprise.example.com",
                    "control_name": "Status Filter",
                    "control_type": "select_dropdown",
                    "action_type": "select",
                    "option_chosen": "Active",
                    "url_before": "https://enterprise.example.com",
                    "url_after": "https://enterprise.example.com",
                    "initial_state_fingerprint": "fp_init_01",
                    "resulting_state_fingerprint": "fp_res_active",
                    "newly_visible_elements": ["Record Active #1"],
                    "visible_text_delta": "Table refreshed to display 14 active records.",
                    "status": "OBSERVED",
                }
            ],
        },
        "discovered_elements": [
            {
                "tag": "select",
                "name": "status-filter",
                "page_url": "https://enterprise.example.com",
                "element_id": "status-filter",
            }
        ],
    }

    knowledge, flow = application_knowledge_service.build_knowledge_and_flow(crawl_data)

    assert len(knowledge.interactive_controls) == 1
    ctrl = knowledge.interactive_controls[0]
    assert ctrl.control_name == "Status Filter"
    assert len(ctrl.options) == 3
    assert len(ctrl.observed_transitions) == 1
    assert ctrl.observed_transitions[0].status == "OBSERVED"

    assert len(knowledge.interactive_observations) == 1
    obs = knowledge.interactive_observations[0]
    assert obs.option_chosen == "Active"
    assert obs.resulting_state_fingerprint == "fp_res_active"

    # Verify flow derives interactive state sequence
    interactive_seqs = [s for s in flow.sequences if "Status Filter" in s.name or "Explore Status Filter" in s.name]
    assert len(interactive_seqs) >= 1
    seq = interactive_seqs[0]
    assert any("Select option 'Active'" in step.action for step in seq.steps)


def test_application_model_generation_and_persistence():
    crawl_data = {
        "crawl_id": "crawl-model-test-02",
        "application_url": "https://crm.example.com",
        "crawl_status": "crawl_completed",
        "page_title": "CRM Home",
        "crawl_report": {
            "pages_completed": 1,
            "page_inventory": [
                {
                    "url": "https://crm.example.com",
                    "title": "CRM Home",
                    "elements": [],
                }
            ],
            "pages_skipped": [
                {"url": "https://crm.example.com/external", "reason": "external_domain"}
            ],
            "interactive_controls": [
                {
                    "control_id": "ctrl_tab_nav",
                    "page_url": "https://crm.example.com",
                    "control_name": "Main Navigation Tabs",
                    "control_type": "tab_list",
                    "verified_locator": "[role='tablist']",
                    "options": [
                        {"label": "Overview", "value": "overview", "is_default_or_selected": True},
                        {"label": "Customers", "value": "customers", "is_default_or_selected": False},
                    ],
                    "observed_transitions": [
                        {
                            "action_type": "click",
                            "option_selected": "Customers",
                            "initial_state_fingerprint": "fp_tab_init",
                            "resulting_state_fingerprint": "fp_tab_cust",
                            "url_before": "https://crm.example.com",
                            "url_after": "https://crm.example.com",
                            "status": "OBSERVED",
                            "visible_changes_observed": "Customer list table loaded with search input.",
                            "newly_visible_elements_count": 5,
                        }
                    ],
                    "exploration_status": "OBSERVED",
                }
            ],
            "interactive_observations": [
                {
                    "observation_id": "obs-2001",
                    "page_url": "https://crm.example.com",
                    "control_name": "Main Navigation Tabs",
                    "control_type": "tab_list",
                    "action_type": "click",
                    "option_chosen": "Customers",
                    "url_before": "https://crm.example.com",
                    "url_after": "https://crm.example.com",
                    "initial_state_fingerprint": "fp_tab_init",
                    "resulting_state_fingerprint": "fp_tab_cust",
                    "status": "OBSERVED",
                }
            ],
        },
        "discovered_elements": [
            {
                "tag": "button",
                "role": "tab",
                "name": "Customers",
                "page_url": "https://crm.example.com",
            }
        ],
    }

    knowledge, flow = application_knowledge_service.build_knowledge_and_flow(crawl_data)
    model = application_knowledge_service.build_application_model(
        knowledge,
        flow,
        crawl_report=crawl_data["crawl_report"],
    )

    assert isinstance(model, ApplicationModel)
    assert model.application_url == "https://crm.example.com"
    assert len(model.modules) >= 1
    assert len(model.confirmed_states) >= 2  # page rendered + interactive transition
    assert any(s["status"] == "OBSERVED" for s in model.confirmed_states)

    # Check unobserved states / skipped items
    assert len(model.unknown_or_unexplored) >= 1
    assert any(item["status"] in {"REQUIRES_FURTHER_EXPLORATION", "UNKNOWN"} for item in model.unknown_or_unexplored)

    # Test persistence and loading
    saved_path = application_knowledge_service.persist_all("crawl-model-test-02", knowledge, flow, model)
    assert saved_path.is_file()

    loaded_model = application_knowledge_service.load_model("crawl-model-test-02")
    assert loaded_model is not None
    assert loaded_model.application_url == "https://crm.example.com"
    assert len(loaded_model.modules) == len(model.modules)
    assert len(loaded_model.interactive_controls) == 1


def test_api_router_model_and_knowledge_endpoints():
    client = TestClient(app)

    # Test crawl model endpoint
    response = client.get("/api/v1/automation/url-crawl/crawl-model-test-02/model")
    assert response.status_code == 200
    data = response.json()
    assert data["crawl_id"] == "crawl-model-test-02"
    assert "application_model" in data
    assert data["application_model"]["application_url"] == "https://crm.example.com"
    assert len(data["application_model"]["interactive_controls"]) == 1

    # Test knowledge endpoint returning model alongside knowledge and flow
    resp_k = client.get("/api/v1/automation/url-crawl/crawl-model-test-02/knowledge")
    assert resp_k.status_code == 200
    data_k = resp_k.json()
    assert data_k["application_knowledge"]["application_url"] == "https://crm.example.com"
    assert data_k["application_flow"]["starting_page"] == "https://crm.example.com"
    assert data_k["application_model"] is not None
