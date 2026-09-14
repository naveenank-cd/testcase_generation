import pytest
from app.schemas.automation_schema import CrawlAnalysisResponse, DiscoveredElement
from app.services.application_knowledge_service import application_knowledge_service


def test_build_knowledge_and_derive_flow_from_crawl_evidence():
    crawl_data = {
        "crawl_id": "crawl-test-123",
        "application_url": "https://example.com",
        "crawl_status": "crawl_completed",
        "page_title": "Example Portal",
        "crawl_report": {
            "pages_completed": 2,
            "page_inventory": [
                {
                    "url": "https://example.com",
                    "title": "Example Portal",
                    "elements": [],
                },
                {
                    "url": "https://example.com/login",
                    "title": "Login Page",
                    "elements": [],
                },
            ],
            "navigation_relationships": [
                {
                    "from": "https://example.com",
                    "to": "https://example.com/login",
                    "via": "Sign In",
                }
            ],
        },
        "discovered_elements": [
            {
                "tag": "a",
                "role": "link",
                "name": "Sign In",
                "visible_text": "Sign In",
                "href": "https://example.com/login",
                "page_url": "https://example.com",
            },
            {
                "tag": "input",
                "input_type": "text",
                "name": "username",
                "label": "Username",
                "placeholder": "Enter username",
                "required": True,
                "page_url": "https://example.com/login",
                "test_id": "username-input",
            },
            {
                "tag": "input",
                "input_type": "password",
                "name": "password",
                "label": "Password",
                "placeholder": "Enter password",
                "required": True,
                "page_url": "https://example.com/login",
                "test_id": "password-input",
            },
            {
                "tag": "button",
                "role": "button",
                "name": "Submit",
                "visible_text": "Log In",
                "page_url": "https://example.com/login",
                "test_id": "login-submit-btn",
            },
        ],
    }

    knowledge, flow = application_knowledge_service.build_knowledge_and_flow(crawl_data)

    # Verify Application Knowledge structure
    assert knowledge.application_url == "https://example.com"
    assert knowledge.crawl_id == "crawl-test-123"
    assert len(knowledge.pages) == 2
    assert len(knowledge.navigation_paths) >= 1
    assert len(knowledge.forms) >= 1
    assert len(knowledge.actions) == 4

    # Verify verified locators are present
    assert any("data-testid=\"username-input\"" in loc for loc in knowledge.verified_locators.values())
    assert any("data-testid=\"password-input\"" in loc for loc in knowledge.verified_locators.values())
    assert any("data-testid=\"login-submit-btn\"" in loc for loc in knowledge.verified_locators.values())

    # Verify Application Flow structure
    assert flow.starting_page == "https://example.com"
    assert len(flow.sequences) >= 2
    assert len(flow.transitions) >= 1
    assert "nodes" in flow.state_graph
    assert "edges" in flow.state_graph


def test_persist_and_load_application_knowledge():
    crawl_data = {
        "crawl_id": "crawl-persist-test",
        "application_url": "https://app.example.com",
        "crawl_status": "crawl_completed",
        "page_title": "App Home",
        "discovered_elements": [
            {
                "tag": "button",
                "name": "Get Started",
                "page_url": "https://app.example.com",
            }
        ],
    }
    knowledge, flow = application_knowledge_service.build_knowledge_and_flow(crawl_data)
    saved_path = application_knowledge_service.persist("test-identifier-1", knowledge, flow)
    assert saved_path.is_file()

    loaded = application_knowledge_service.load("test-identifier-1")
    assert loaded is not None
    loaded_k, loaded_f = loaded
    assert loaded_k.application_url == "https://app.example.com"
    assert loaded_f.starting_page == "https://app.example.com"


@pytest.mark.asyncio
async def test_context_preparation_attaches_application_knowledge():
    from app.agents.base_agent import ExecutionContext
    from app.agents.context_preparation_agent import ContextPreparationAgent

    crawl_data = {
        "crawl_id": "crawl-ctx-test",
        "application_url": "https://portal.example.com",
        "crawl_status": "crawl_completed",
        "page_title": "Portal",
        "discovered_elements": [
            {
                "tag": "button",
                "name": "Sign In",
                "page_url": "https://portal.example.com",
                "test_id": "signin-btn",
            }
        ],
    }
    knowledge, flow = application_knowledge_service.build_knowledge_and_flow(crawl_data)
    application_knowledge_service.persist("crawl-ctx-test", knowledge, flow)

    input_payload = {
        "user_stories": ["As a customer, I want to sign in to access my portal."],
        "acceptance_criteria": ["Given valid credentials, when I sign in, then portal opens."],
        "crawl_id": "crawl-ctx-test",
    }
    ctx = ExecutionContext(request_id="test-req-1", workflow_id="test-wf-1", metadata={"mock_mode": True})
    agent = ContextPreparationAgent()
    structured = await agent.run({"input_payload": input_payload, "project_id": None}, ctx)

    assert structured.application_knowledge is not None
    assert structured.application_knowledge["application_url"] == "https://portal.example.com"
    assert structured.application_flow is not None
    assert structured.application_flow["starting_page"] == "https://portal.example.com"

