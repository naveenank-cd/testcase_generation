import uuid
from app.agents.base_agent import BaseAgent, ExecutionContext
from app.schemas.context_schema import StructuredContext, TraceabilityEntry
from app.schemas.input_schema import ManualInputPayload
from app.schemas.common import SourceType
from app.utils.validators import deduplicate, item_id, item_text
from app.image_processing.image_pipeline import ImagePipeline
from app.image_processing.context_fusion import fuse
from app.services.application_knowledge_service import application_knowledge_service

PREFIXES = {
    "functional_requirements": "REQ",
    "non_functional_requirements": "NFR",
    "epics": "EPIC",
    "features": "FEAT",
    "user_stories": "US",
    "acceptance_criteria": "AC",
    "business_rules": "BR",
    "dependencies": "DEP",
    "constraints": "CON",
}

def _structured_items(items, prefix):
    structured = []
    for index, item in enumerate(items):
        if isinstance(item, dict):
            normalized = dict(item)
            normalized.setdefault("id", item_id(item, prefix, index))
            if not any(normalized.get(key) for key in ("text", "title", "description", "name")):
                normalized["text"] = item_text(item)
        else:
            normalized = {"id": item_id(item, prefix, index), "text": item_text(item)}
        structured.append(normalized)
    return structured

class ContextPreparationAgent(BaseAgent[StructuredContext]):
    output_model = StructuredContext
    async def run(self, input_data, execution_context: ExecutionContext) -> StructuredContext:
        payload = ManualInputPayload.model_validate(input_data.get("input_payload", input_data)).model_dump()
        for key, value in payload.items():
            if isinstance(value, list):
                payload[key] = deduplicate(value)
        if not payload["user_stories"]:
            raise ValueError("At least one user story is required")
        for key, prefix in PREFIXES.items():
            payload[key] = _structured_items(payload[key], prefix)
        stories = payload["user_stories"]
        criteria = payload["acceptance_criteria"]
        for index, criterion in enumerate(criteria):
            if criterion.get("user_story_id"):
                continue
            if len(stories) == 1:
                criterion["user_story_id"] = str(stories[0]["id"])
            elif len(criteria) == len(stories):
                criterion["user_story_id"] = str(stories[index]["id"])

        # Load persisted knowledge/flow if crawl_id or workflow_id is available and not directly in payload
        app_knowledge = payload.get("application_knowledge")
        app_flow = payload.get("application_flow")
        crawl_id = payload.get("crawl_id")
        app_url = payload.get("application_url")

        if not app_knowledge:
            workflow_id = input_data.get("workflow_id")
            for id_to_check in filter(None, [crawl_id, workflow_id, input_data.get("project_id")]):
                loaded = application_knowledge_service.load(id_to_check)
                if loaded:
                    app_knowledge, app_flow = loaded[0].model_dump(mode="json"), loaded[1].model_dump(mode="json")
                    if not app_url:
                        app_url = loaded[0].application_url
                    break

        payload["application_knowledge"] = app_knowledge
        payload["application_flow"] = app_flow
        payload["application_url"] = app_url
        payload["crawl_id"] = crawl_id

        visual_context = []
        for image_id in payload.get("image_ids", []):
            record = ImagePipeline.get(image_id)
            if record:
                visual_context.append(record["compact_context"])
        payload["visual_context"] = [fuse(payload, visual_context)] if visual_context else []
        shared_target_ids = [
            str(item["id"])
            for key in (
                "functional_requirements",
                "non_functional_requirements",
                "epics",
                "features",
                "business_rules",
                "dependencies",
                "constraints",
            )
            for item in payload[key]
        ]
        trace = []
        for story in payload["user_stories"]:
            story_id = str(story["id"])
            criterion_ids = [str(item["id"]) for item in payload["acceptance_criteria"] if str(item.get("user_story_id", "")) == story_id]
            trace.append(TraceabilityEntry(source_id=story_id, target_ids=shared_target_ids + criterion_ids))
        return StructuredContext(
            project_id=input_data.get("project_id") or uuid.uuid4(),
            source_type=input_data.get("source_type", SourceType.manual),
            traceability_map=trace,
            metadata={"normalized": True},
            **payload,
        )

