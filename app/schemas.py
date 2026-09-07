from pydantic import BaseModel
from typing import Optional

class QueryRequest(BaseModel):
    user_id: str
    prompt: str
    model_hint: Optional[str] = None  # e.g., "ultra", "super", "nano"
    use_memory: bool = True

class QueryResponse(BaseModel):
    reply: str
    model_used: Optional[str] = None