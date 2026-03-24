from pydantic import BaseModel, Field, SecretStr
from typing import Optional
from database.models.enums import MembersPermissions

class CreateWorkspaceRequest(BaseModel):
    name: str = Field(..., description="Name of the workspace")


class PatchWorkspaceRequest(BaseModel):
    git_access_token: Optional[str] = Field(description='Git provider personal access token', default=None)

class AssignWorkspaceRequest(BaseModel):
    permission: MembersPermissions
    user_email: str = Field(..., description="Email of the user to be assigned to the workspace")