from fastapi import APIRouter, HTTPException, status, Depends
from requests.exceptions import ConnectionError, HTTPError

from auth.permission_authorizer import Authorizer
from clients.chat_rest_client import ChatRestClient
from core.logger import get_configured_logger
from database.models.enums import Permission
from schemas.requests.chat import ChatRequest
from schemas.responses.chat import ChatResponse
from schemas.errors.base import SomethingWrongError


router = APIRouter(prefix="/workspaces/{workspace_id}/chat")

read_authorizer = Authorizer(permission_level=Permission.read.value)

chat_client = ChatRestClient()
logger = get_configured_logger("chat_router")


@router.post(
    path="",
    status_code=200,
    responses={
        status.HTTP_200_OK: {"model": ChatResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": SomethingWrongError},
    },
    dependencies=[Depends(read_authorizer.authorize)],
)
def send_chat_message(
    workspace_id: int,
    body: ChatRequest,
) -> ChatResponse:
    """Forward a chat message to the external chat app and return its response."""
    try:
        data = chat_client.send_message(
            messages=[m.model_dump() for m in body.messages],
            workspace_id=workspace_id,
        )
        logger.info(f"Raw response from chat service: {data}")

        workflow_raw = data.get("workflow")
        logger.info(f"Workflow field type: {type(workflow_raw).__name__}, value: {workflow_raw}")

        try:
            response = ChatResponse(**data)
            logger.info(f"ChatResponse.workflow type after parsing: {type(response.workflow).__name__}")
            return response
        except Exception as parse_err:
            logger.error(f"Failed to construct ChatResponse from data: {parse_err}. Raw data: {data}")
            raise
    except (HTTPError, ConnectionError) as e:
        raise HTTPException(status_code=502, detail=str(e))
