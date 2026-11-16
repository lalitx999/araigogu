import secrets
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException

from . import service
from .config import Settings, get_settings
from .llm import LLM
from .schemas import (
    ChatRequest, ChatResponse, CommentRequest, CommentResponse,
    ModerateRequest, ModerateResponse,
)

app = FastAPI(title="Arai Go Gu AI Service", version="0.1.0")


@lru_cache
def get_llm() -> LLM:
    return LLM(get_settings())


def require_token(
    x_internal_token: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> None:
    if not secrets.compare_digest(x_internal_token, settings.ai_internal_token):
        raise HTTPException(status_code=401, detail="invalid token")


@app.get("/health")
def health(llm: LLM = Depends(get_llm)):
    return {"status": "ok", "llm_configured": llm.available}


@app.post("/v1/chat", response_model=ChatResponse, dependencies=[Depends(require_token)])
async def chat(req: ChatRequest, llm: LLM = Depends(get_llm)):
    return await service.chat(llm, req)


@app.post("/v1/moderate", response_model=ModerateResponse, dependencies=[Depends(require_token)])
async def moderate(req: ModerateRequest, llm: LLM = Depends(get_llm)):
    return await service.moderate(llm, req)


@app.post("/v1/comment", response_model=CommentResponse, dependencies=[Depends(require_token)])
async def comment(req: CommentRequest, llm: LLM = Depends(get_llm)):
    return await service.comment(llm, req)
