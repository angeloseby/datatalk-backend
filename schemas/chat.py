from pydantic import BaseModel
from typing import Optional, Any, Dict

class ChatRequest(BaseModel):
    file_id: str
    question: str

# This is what we return immediately (The Receipt)
class ChatJobResponse(BaseModel):
    job_id: str
    message: str = "AI is thinking..."

# This is the structure of the FINAL result stored in the tracker
class ChatResult(BaseModel):
    answer: str
    generated_code: Optional[str] = None
    data: Optional[Dict[str, Any]] = None