from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core.config import settings
from app.schemas.application_knowledge_schema import (
    ApplicationFlow,
    ApplicationKnowledge,
    DiscoveredActionInfo,
    DiscoveredFormFieldInfo,
    DiscoveredFormInfo,
    DiscoveredPageInfo,
    FlowSequence,
    FlowStep,
    FlowTransition,
    NavigationPathInfo,
)
from app.schemas.automation_schema import CrawlAnalysisResponse, DiscoveredElement

logger = logging.getLogger(__name__)


def _canonical_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return url.strip().rstrip("/")
    path = parsed.path.rstrip("/") if parsed.path else ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"



def _infer_module_name(url: str, base_url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path.strip("/")
    if not path:
        return "Home / Landing"
    segments = path.split("/")
    first = segments[0].replace("-", " ").replace("_", " ").title()
    if len(segments) > 1:
        second = segments[1].replace("-", " ").replace("_", " ").title()
        return f"{first} / {second}"
    return first


def _element_display_name(el: DiscoveredElement | dict[str, Any]) -> str:
    if isinstance(el, DiscoveredElement):
        name = el.name or el.aria_label or el.label or el.visible_text or el.placeholder or el.test_id or el.tag
    else:
        name = (
            el.get("name")
            or el.get("aria_label")
            or el.get("label")
            or el.get("visible_text")
            or el.get("placeholder")
            or el.get("test_id")
            or el.get("tag")
            or "Interactive Element"
        )
    return str(name).strip()[:80] or "Element"


def _element_best_locator(el: DiscoveredElement | dict[str, Any]) -> str:
    if isinstance(el, DiscoveredElement):
        if el.test_id:
            return f'[data-testid="{el.test_id}"]'
        if el.role and el.name:
            return f'page.get_by_role("{el.role}", name="{el.name}")'
        if el.label:
            return f'page.get_by_label("{el.label}")'
        if el.placeholder:
            return f'page.get_by_placeholder("{el.placeholder}")'
        if el.visible_text:
            return f'page.get_by_text("{el.visible_text.strip()[:50]}")'
        if el.css_selector:
            return el.css_selector
        return el.tag
    else:
        if el.get("test_id"):
            return f'[data-testid="{el["test_id"]}"]'
        if el.get("role") and el.get("name"):
            return f'page.get_by_role("{el["role"]}", name="{el["name"]}")'
        if el.get("label"):
            return f'page.get_by_label("{el["label"]}")'
        if el.get("placeholder"):
            return f'page.get_by_placeholder("{el["placeholder"]}")'
        if el.get("visible_text"):
            return f'page.get_by_text("{str(el["visible_text"]).strip()[:50]}")'
        if el.get("css_selector"):
            return str(el["css_selector"])
        return str(el.get("tag", "button"))


class ApplicationKnowledgeService:
    """Extracts, structures, and manages verified Application Knowledge and Flow from real crawl evidence."""

    def __init__(self):
        self.artifact_root = Path(settings.automation_artifacts_path) / "knowledge"

    def _storage_path(self, identifier: str) -> Path:
        return self.artifact_root / f"{re.sub(r'[^a-zA-Z0-9_-]+', '-', str(identifier))}.json"

    def build_knowledge_and_flow(
        self,
        crawl_data: CrawlAnalysisResponse | dict[str, Any],
        workflow_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> tuple[ApplicationKnowledge, ApplicationFlow]:
        """Pure deterministic extractor: guarantees actual discovered elements only without invention."""
        if isinstance(crawl_data, CrawlAnalysisResponse):
            crawl_dict = crawl_data.model_dump(mode="json")
        else:
            crawl_dict = dict(crawl_data)

        app_url = _canonical_url(str(crawl_dict.get("application_url", "")))
        crawl_id = str(crawl_dict.get("crawl_id", ""))
        crawl_status = crawl_dict.get("crawl_status", "crawl_completed")
        crawl_report = crawl_dict.get("crawl_report", {}) or {}
        app_map = crawl_dict.get("application_map", {}) or {}
        raw_elements = crawl_dict.get("discovered_elements", []) or []

        # Convert raw elements to DiscoveredElement objects
        discovered_elements: list[DiscoveredElement] = []
        for item in raw_elements:
            if isinstance(item, DiscoveredElement):
                discovered_elements.append(item)
            elif isinstance(item, dict):
                try:
                    discovered_elements.append(DiscoveredElement.model_validate(item))
                except Exception:
                    pass

        # 1. Group elements by canonical page URL
        elements_by_page: dict[str, list[DiscoveredElement]] = {}
        for elem in discovered_elements:
            elem_page = _canonical_url(elem.page_url or app_url)
            elements_by_page.setdefault(elem_page, []).append(elem)

        # 2. Build DiscoveredPageInfo list
        page_inventory = crawl_report.get("page_inventory", []) or app_map.get("pages", []) or []
        pages: list[DiscoveredPageInfo] = []
        seen_urls: set[str] = set()

        for p in page_inventory:
            p_url = _canonical_url(str(p.get("url") or p.get("final_url") or app_url))
            if p_url in seen_urls:
                continue
            seen_urls.add(p_url)
            parsed = urlsplit(p_url)
            page_elems = elements_by_page.get(p_url, [])
            interactive_count = sum(
                1 for e in page_elems if e.tag in {"button", "a", "input", "select", "textarea"} or e.role in {"button", "link", "textbox", "combobox", "checkbox", "radio"}
            )
            form_count = sum(1 for e in page_elems if e.tag == "form" or e.form_info is not None)
            pages.append(
                DiscoveredPageInfo(
                    url=p_url,
                    route_path=parsed.path or "/",
                    title=str(p.get("title") or (crawl_dict.get("page_title") if p_url == app_url else None) or parsed.path or "Page"),
                    module_name=_infer_module_name(p_url, app_url),
                    element_count=len(page_elems),
                    interactive_elements_count=interactive_count,
                    form_count=form_count,
                    is_authenticated_page=bool(p.get("is_authenticated") or p.get("authenticated")),
                )
            )

        if not pages and app_url:
            parsed = urlsplit(app_url)
            page_elems = elements_by_page.get(app_url, [])
            pages.append(
                DiscoveredPageInfo(
                    url=app_url,
                    route_path=parsed.path or "/",
                    title=crawl_dict.get("page_title") or "Home Page",
                    module_name="Home",
                    element_count=len(page_elems),
                    interactive_elements_count=len(page_elems),
                    form_count=0,
                )
            )

        # 3. Extract DiscoveredActionInfo & verified locators
        actions: list[DiscoveredActionInfo] = []
        verified_locators: dict[str, str] = {}

        for elem in discovered_elements:
            elem_page = _canonical_url(elem.page_url or app_url)
            locator = _element_best_locator(elem)
            name = _element_display_name(elem)
            key = f"{elem_page}:{name}"
            verified_locators[key] = locator

            action_type = "click"
            if elem.tag == "input":
                itype = str(elem.input_type or "").lower()
                if itype in {"checkbox"}:
                    action_type = "check"
                elif itype in {"radio"}:
                    action_type = "select"
                elif itype in {"submit", "button"}:
                    action_type = "click"
                else:
                    action_type = "fill"
            elif elem.tag in {"textarea"}:
                action_type = "fill"
            elif elem.tag in {"select"}:
                action_type = "select"
            elif elem.tag == "a" and elem.href:
                action_type = "navigate"
            elif elem.tag == "form":
                action_type = "submit"

            target_url = None
            if elem.href:
                target_url = _canonical_url(str(elem.href))

            actions.append(
                DiscoveredActionInfo(
                    page_url=elem_page,
                    action_type=action_type,  # type: ignore[arg-type]
                    element_name=name,
                    element_role=elem.role,
                    element_tag=elem.tag,
                    verified_locator=locator,
                    target_url=target_url,
                    input_type=elem.input_type,
                    required=bool(elem.required),
                )
            )

        # 4. Extract Navigation Paths
        navigation_paths: list[NavigationPathInfo] = []
        raw_relationships = crawl_report.get("navigation_relationships", []) or app_map.get("relationships", []) or []
        for rel in raw_relationships:
            from_u = _canonical_url(str(rel.get("from") or rel.get("from_url") or app_url))
            to_u = _canonical_url(str(rel.get("to") or rel.get("to_url") or ""))
            via_name = str(rel.get("via") or rel.get("via_element") or "Navigation Link")
            if from_u and to_u:
                navigation_paths.append(
                    NavigationPathInfo(
                        from_url=from_u,
                        to_url=to_u,
                        via_element_name=via_name,
                        verified_locator=f'page.get_by_role("link", name="{via_name}")' if via_name else None,
                        action_type="click",
                    )
                )

        # Fallback navigation paths from discovered elements with same-origin href
        origin = urlsplit(app_url).netloc
        for elem in discovered_elements:
            if elem.href and elem.tag == "a":
                h_url = _canonical_url(str(elem.href))
                if urlsplit(h_url).netloc == origin:
                    from_u = _canonical_url(elem.page_url or app_url)
                    if from_u != h_url and not any(np.from_url == from_u and np.to_url == h_url for np in navigation_paths):
                        navigation_paths.append(
                            NavigationPathInfo(
                                from_url=from_u,
                                to_url=h_url,
                                via_element_name=_element_display_name(elem),
                                verified_locator=_element_best_locator(elem),
                                action_type="click",
                            )
                        )

        # 5. Extract Discovered Forms
        forms: list[DiscoveredFormInfo] = []
        for page_obj in pages:
            p_elems = elements_by_page.get(page_obj.url, [])
            input_fields: list[DiscoveredFormFieldInfo] = []
            submit_btn: str | None = None
            submit_loc: str | None = None

            for e in p_elems:
                if e.tag in {"input", "textarea", "select"} and (e.input_type or "").lower() not in {"submit", "button", "hidden"}:
                    input_fields.append(
                        DiscoveredFormFieldInfo(
                            name=e.name,
                            label=e.label or e.aria_label or e.placeholder,
                            input_type=e.input_type or ("textarea" if e.tag == "textarea" else "text"),
                            placeholder=e.placeholder,
                            required=bool(e.required),
                            verified_locator=_element_best_locator(e),
                        )
                    )
                elif e.tag in {"button", "input"} and (e.role == "button" or (e.input_type or "").lower() in {"submit", "button"}):
                    if not submit_btn:
                        submit_btn = _element_display_name(e)
                        submit_loc = _element_best_locator(e)

            if input_fields:
                forms.append(
                    DiscoveredFormInfo(
                        page_url=page_obj.url,
                        form_name=f"{page_obj.title} Form" if page_obj.title else "Discovered Form",
                        fields=input_fields,
                        submit_button_name=submit_btn,
                        submit_locator=submit_loc,
                    )
                )

        summary = {
            "total_pages": len(pages),
            "total_elements": len(discovered_elements),
            "total_actions": len(actions),
            "total_navigation_paths": len(navigation_paths),
            "total_forms": len(forms),
            "crawl_status": crawl_status,
            "application_url": app_url,
        }

        knowledge = ApplicationKnowledge(
            application_url=app_url,
            crawl_id=crawl_id,
            workflow_id=workflow_id,
            project_id=project_id,
            crawl_status=crawl_status if crawl_status in {"crawl_completed", "crawl_incomplete", "crawl_blocked"} else "crawl_completed",  # type: ignore[arg-type]
            pages=pages,
            elements_by_page=elements_by_page,
            actions=actions,
            navigation_paths=navigation_paths,
            forms=forms,
            verified_locators=verified_locators,
            summary=summary,
        )

        # 6. Derive Application Flow
        flow = self._derive_application_flow(knowledge, navigation_paths, pages, forms, actions)
        return knowledge, flow

    def _derive_application_flow(
        self,
        knowledge: ApplicationKnowledge,
        navigation_paths: list[NavigationPathInfo],
        pages: list[DiscoveredPageInfo],
        forms: list[DiscoveredFormInfo],
        actions: list[DiscoveredActionInfo],
    ) -> ApplicationFlow:
        """Derives structured multi-step user journey sequences and graph transitions strictly from crawl evidence."""
        start_page = knowledge.application_url
        transitions: list[FlowTransition] = []
        for np in navigation_paths:
            transitions.append(
                FlowTransition(
                    from_page=np.from_url,
                    to_page=np.to_url,
                    action=f"Click on '{np.via_element_name}'",
                    element_name=np.via_element_name,
                    verified_locator=np.verified_locator,
                    conditions=[],
                )
            )

        # Build Flow Sequences
        sequences: list[FlowSequence] = []
        seq_idx = 1

        # 1. Primary Entry Flow / Home exploration
        home_page = next((p for p in pages if p.url == start_page), pages[0] if pages else None)
        if home_page:
            home_steps: list[FlowStep] = [
                FlowStep(
                    step_number=1,
                    page_url=home_page.url,
                    page_title=home_page.title,
                    action=f"Navigate to application root: '{home_page.url}'",
                    element_name=None,
                    verified_locator=None,
                    expected_state_change=f"Page '{home_page.title}' loads successfully.",
                )
            ]
            step_num = 2
            # Add interactive actions discovered on home page
            for act in actions:
                if act.page_url == home_page.url and act.action_type in {"click", "fill", "submit"}:
                    home_steps.append(
                        FlowStep(
                            step_number=step_num,
                            page_url=home_page.url,
                            page_title=home_page.title,
                            action=f"{act.action_type.title()} '{act.element_name}'",
                            element_name=act.element_name,
                            verified_locator=act.verified_locator,
                            target_page_url=act.target_url,
                            expected_state_change=f"Perform {act.action_type} on {act.element_name}.",
                        )
                    )
                    step_num += 1
                    if step_num > 6:
                        break

            sequences.append(
                FlowSequence(
                    sequence_id=f"seq-{seq_idx:03d}",
                    name=f"Explore {home_page.title or 'Landing Page'}",
                    description=f"Primary interaction flow on {home_page.title}",
                    starting_page=home_page.url,
                    destination_page=home_page.url,
                    steps=home_steps,
                    identified_module=home_page.module_name,
                )
            )
            seq_idx += 1

        # 2. Form Submission Sequences
        for form in forms:
            f_page = next((p for p in pages if p.url == form.page_url), None)
            f_steps: list[FlowStep] = [
                FlowStep(
                    step_number=1,
                    page_url=form.page_url,
                    page_title=f_page.title if f_page else "Form Page",
                    action=f"Navigate to page '{form.page_url}'",
                    expected_state_change="Form displays with interactive input fields.",
                )
            ]
            f_num = 2
            for f_field in form.fields:
                f_name = f_field.label or f_field.name or "Input field"
                f_steps.append(
                    FlowStep(
                        step_number=f_num,
                        page_url=form.page_url,
                        page_title=f_page.title if f_page else "Form Page",
                        action=f"Enter valid data into '{f_name}'",
                        element_name=f_name,
                        verified_locator=f_field.verified_locator,
                        expected_state_change=f"Field '{f_name}' accepts input.",
                        dependencies=["Required field"] if f_field.required else [],
                    )
                )
                f_num += 1
            if form.submit_button_name:
                f_steps.append(
                    FlowStep(
                        step_number=f_num,
                        page_url=form.page_url,
                        page_title=f_page.title if f_page else "Form Page",
                        action=f"Click '{form.submit_button_name}' button",
                        element_name=form.submit_button_name,
                        verified_locator=form.submit_locator,
                        expected_state_change="Form submission triggers validation / processing.",
                    )
                )

            sequences.append(
                FlowSequence(
                    sequence_id=f"seq-{seq_idx:03d}",
                    name=f"Submit {form.form_name}",
                    description=f"Complete and submit form fields on {form.page_url}",
                    starting_page=form.page_url,
                    destination_page=form.page_url,
                    steps=f_steps,
                    identified_module=f_page.module_name if f_page else "Forms",
                )
            )
            seq_idx += 1

        # 3. Navigation Branch Sequences (from start page to other discovered pages)
        for dest_page in pages:
            if dest_page.url == start_page:
                continue
            # Find path from start_page to dest_page
            path_item = next((np for np in navigation_paths if np.to_url == dest_page.url), None)
            branch_steps: list[FlowStep] = [
                FlowStep(
                    step_number=1,
                    page_url=start_page,
                    action=f"Start on entry page '{start_page}'",
                    expected_state_change="Initial application view is loaded.",
                ),
                FlowStep(
                    step_number=2,
                    page_url=path_item.from_url if path_item else start_page,
                    action=f"Click '{path_item.via_element_name if path_item else dest_page.title}' to navigate",
                    element_name=path_item.via_element_name if path_item else dest_page.title,
                    verified_locator=path_item.verified_locator if path_item else None,
                    target_page_url=dest_page.url,
                    expected_state_change=f"URL transitions to '{dest_page.url}' and view renders '{dest_page.title}'.",
                ),
            ]
            # Add element interaction on dest_page
            dest_acts = [a for a in actions if a.page_url == dest_page.url]
            if dest_acts:
                first_act = dest_acts[0]
                branch_steps.append(
                    FlowStep(
                        step_number=3,
                        page_url=dest_page.url,
                        page_title=dest_page.title,
                        action=f"{first_act.action_type.title()} '{first_act.element_name}' on target page",
                        element_name=first_act.element_name,
                        verified_locator=first_act.verified_locator,
                        expected_state_change=f"Verify target page controls on '{dest_page.title}'.",
                    )
                )

            sequences.append(
                FlowSequence(
                    sequence_id=f"seq-{seq_idx:03d}",
                    name=f"Navigate to {dest_page.title}",
                    description=f"Journey from entry page to {dest_page.route_path} ({dest_page.title})",
                    starting_page=start_page,
                    destination_page=dest_page.url,
                    steps=branch_steps,
                    identified_module=dest_page.module_name,
                )
            )
            seq_idx += 1

        # Build Graph
        state_graph = {
            "nodes": [
                {"id": p.url, "label": p.title or p.route_path, "route": p.route_path, "module": p.module_name}
                for p in pages
            ],
            "edges": [
                {"source": t.from_page, "target": t.to_page, "label": t.element_name, "action": t.action}
                for t in transitions
            ],
        }

        return ApplicationFlow(
            flow_id=f"flow-{uuid.uuid4()}",
            application_url=start_page,
            starting_page=start_page,
            sequences=sequences,
            transitions=transitions,
            state_graph=state_graph,
        )

    def persist(
        self,
        identifier: str | uuid.UUID,
        knowledge: ApplicationKnowledge,
        flow: ApplicationFlow,
    ) -> Path:
        """Persists Application Knowledge and Application Flow to disk."""
        path = self._storage_path(str(identifier))
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "knowledge": knowledge.model_dump(mode="json"),
            "flow": flow.model_dump(mode="json"),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Persisted Application Knowledge and Flow to %s", path)
        return path

    def load(
        self,
        identifier: str | uuid.UUID,
    ) -> tuple[ApplicationKnowledge, ApplicationFlow] | None:
        """Loads persisted Application Knowledge and Flow."""
        path = self._storage_path(str(identifier))
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            k = ApplicationKnowledge.model_validate(data["knowledge"])
            f = ApplicationFlow.model_validate(data["flow"])
            return k, f
        except Exception as exc:
            logger.warning("Could not load knowledge/flow for %s: %s", identifier, exc)
            return None


application_knowledge_service = ApplicationKnowledgeService()
