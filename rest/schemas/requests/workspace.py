from pydantic import BaseModel, Field
from database.models.enums import MembersPermissions

class CreateWorkspaceRequest(BaseModel):
    name: str = Field(..., description="Name of the workspace")


class PatchWorkspaceRequest(BaseModel):
    name: str | None = Field(default=None, description="New workspace name")

class AssignWorkspaceRequest(BaseModel):
    permission: MembersPermissions
    user_email: str = Field(..., description="Email of the user to be assigned to the workspace")
