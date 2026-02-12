from pydantic import BaseModel, Field

class SecretsModel(BaseModel):
    LOCAL_TEST_SECRET: str = Field(title='Local Test Secret', default='')


class InputModel(BaseModel):
    base_folder: str = Field(title='Base Folder', default='')


class LocalStoragePiece(BaseModel):
    name: str = Field(title='Name', default='LocalStoragePiece')
    description: str = Field(title='Description', default='Local Storage Default Piece')

    secrets_schema: dict = Field(default=SecretsModel.schema())
    input_schema: dict = Field(default=InputModel.schema())