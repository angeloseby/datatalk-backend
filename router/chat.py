import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks
from schemas.chat import ChatRequest, ChatJobResponse
from services.ai_analyst import AIAnalyst
from core.status_tracker import tracker

router = APIRouter(prefix="/chat", tags=["AI Analyst"])
analyst = AIAnalyst()

@router.post("/ask", response_model=ChatJobResponse)
async def ask_question(
    request: ChatRequest, 
    background_tasks: BackgroundTasks
):
    """
    Starts an asynchronous AI analysis job.
    Returns a job_id immediately. Use GET /chat/status/{job_id} to poll for results.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
        
    # 1. Generate a specific Job ID for this chat interaction
    job_id = str(uuid.uuid4())
    
    # 2. Initialize the Tracker
    await tracker.create_job(job_id)
    
    # 3. Queue the background work
    background_tasks.add_task(
        analyst.analyze_background,
        job_id=job_id,
        file_id=request.file_id,
        question=request.question
    )
    
    return ChatJobResponse(job_id=job_id, message="AI is processing your question...")

@router.get("/status/{job_id}")
async def get_chat_status(job_id: str):
    """
    Reusing the generic tracker to check chat status.
    """
    status = await tracker.get_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status