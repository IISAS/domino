import json
import logging
from typing import Optional

from pydantic import BaseModel, model_validator

logger = logging.getLogger(__name__)


class ChatResponse(BaseModel):
    message: str
    workflow: Optional[dict] = None

    @model_validator(mode="before")
    @classmethod
    def parse_workflow_string(cls, values):
        workflow = values.get("workflow")
        if workflow is None:
            logger.info("Workflow field is absent or None - no workflow in response")
        elif isinstance(workflow, str):
            logger.info(f"Workflow is a string, attempting JSON parse. Length: {len(workflow)}")
            try:
                values["workflow"] = json.loads(workflow)
                logger.info("Workflow string parsed successfully into dict")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse workflow string as JSON: {e}. Raw value: {workflow[:500]!r}")
                raise
        elif isinstance(workflow, dict):
            logger.info(f"Workflow is already a dict with keys: {list(workflow.keys())}")
        else:
            logger.error(f"Unexpected workflow type: {type(workflow).__name__}, value: {workflow!r}")
        return values
