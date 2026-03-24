from pydantic import BaseModel, Field
from typing import Optional, List

class WorkspaceAuthorizerData(BaseModel):
    id: int
    name: str
    git_access_token: Optional[str] = None
    user_permission: str


class AuthorizationContextData(BaseModel):
    user_id: int = Field(title='User id')
    workspace: Optional[WorkspaceAuthorizerData] = Field(title='Workspace', default=None)