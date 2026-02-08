import pandas as pd
import os
import asyncio
from core.status_tracker import tracker, JobStatus
from schemas.chat import ChatResult

class AIAnalyst:
    def __init__(self):
        self.processed_dir = "storage/processed"

    def _get_file_path(self, file_id: str) -> str:
        return f"{self.processed_dir}/{file_id}.parquet"

    async def analyze_background(self, job_id: str, file_id: str, question: str):
        """
        Runs in background. Updates StatusTracker with progress and final result.
        """
        try:
            # 1. Update Status: Starting
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Loading data...", 10)
            
            file_path = self._get_file_path(file_id)
            
            # Check file existence
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File {file_id} not found. Please upload again.")

            # 2. Update Status: Thinking (Simulating LLM delay)
            await tracker.update_status(job_id, JobStatus.PROCESSING, "AI is analyzing schema...", 30)
            
            # Load Data
            df = pd.read_parquet(file_path)
            
            # 3. Update Status: Generating Code
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Generating Python code...", 60)
            
            # --- REAL AI LOGIC (Simulated for now) ---
            # Simulate a slight delay for realism
            await asyncio.sleep(2) 
            
            mock_code = f"# Calculated based on: {question}\ndf.describe()"
            mock_answer = f"I analyzed {len(df)} rows. Here is the answer for: '{question}'"
            result_data = df.describe().to_dict()

            # 4. Update Status: Saving Result
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Finalizing answer...", 90)

            # 5. Success! Store the ChatResult in the tracker
            final_result = ChatResult(
                answer=mock_answer,
                generated_code=mock_code,
                data=result_data
            ).model_dump() # Convert pydantic to dict
            
            await tracker.set_result(job_id, final_result)

        except Exception as e:
            await tracker.set_error(job_id, str(e))