from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class Message(BaseModel):
    message: str
    conversation_id: str | None = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class BaseUser(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr


class UserCreate(BaseUser):
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


class CreateUser(UserCreate):
    pass


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    image_file: str | None
    image_path: str


class UserResponse(UserPublic):
    email: EmailStr


class UserPrivate(UserResponse):
    pass


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: EmailStr | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


class PasswordReset(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetRequestResponse(BaseModel):
    message: str
    reset_url: str | None = None


class RegistrationResponse(BaseModel):
    user: UserResponse
    message: str


class Token(BaseModel):
    access_token: str
    token_type: str
