from pydantic import BaseModel
from typing import Optional, Any, Dict, List


class ChatMessage(BaseModel):
    """A single turn in the conversation history."""
    role: str       # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    file_id: str
    question: str
    history: List[ChatMessage] = []


# This is what we return immediately (The Receipt)
class ChatJobResponse(BaseModel):
    job_id: str
    message: str = "AI is thinking..."


# This is the structure of the FINAL result stored in the tracker
class ChatResult(BaseModel):
    summary: str
    generated_code: Optional[str] = None
    table: Optional[List[Dict[str, Any]]] = None
    chart: Optional[Dict[str, Any]] = None
    clarification: Optional[str] = None
