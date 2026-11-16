from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    language: str = Field(default="ja", max_length=10)
    difficulty: str = Field(default="beginner", max_length=20)
    language_name: str = Field(default="", max_length=60)   # Thai display name sent by the web app (120 languages)
    learning_goal: str = Field(default="", max_length=1000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


class ChatResponse(BaseModel):
    reply: str
    topic: str
    degraded: bool = False


class ModerateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class ModerateResponse(BaseModel):
    moderated: bool
    new_content: str
    reason: str
    topic: str = "general"
    confidence: float = 0.0
    # True when the LLM was unavailable and the verdict is NOT a real review.
    degraded: bool = False


class CommentRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    topic: str | None = Field(default=None, max_length=40)


class CommentResponse(BaseModel):
    comment: str
    degraded: bool = False
