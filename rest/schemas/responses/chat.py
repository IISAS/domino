from typing import Optional

from pydantic import BaseModel


class ChatResponse(BaseModel):
    message: str
    workflow: Optional[dict] = None
