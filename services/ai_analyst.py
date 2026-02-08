from io import StringIO
import pandas as pd
import google.generativeai as genai
import os
import asyncio
from core.status_tracker import tracker, JobStatus
from schemas.chat import ChatResult
from config.settings import settings

class AIAnalyst:
    def __init__(self):
        self.processed_dir = "storage/processed"
        
        # Configure Gemini
        if not settings.ai.gemini_api_key:
            print("WARNING: GEMINI_API_KEY is missing in .env")
        else:
            genai.configure(api_key=settings.ai.gemini_api_key)
            self.model = genai.GenerativeModel('gemini-3-flash-preview') # Or 'gemini-pro'

    def _get_file_path(self, file_id: str) -> str:
        return f"{self.processed_dir}/{file_id}.parquet"

    def _generate_prompt(self, df: pd.DataFrame, question: str) -> str:
        """
        Creates a prompt that forces the LLM to write specific Pandas code.
        """
        buffer = StringIO()
        df.info(buf=buffer)
        schema_info = buffer.getvalue()
        
        return f"""
        You are a generic Python Data Analyst. 
        You are given a Pandas DataFrame named 'df'.
        
        DataFrame Schema Info:
        {schema_info}
        
        User Question: {question}
        
        Your Task:
        1. Write a valid Python code snippet using Pandas to answer the question.
        2. ASSIGN the final answer to a variable named 'result'.
        3. The 'result' variable can be a number, string, dataframe, or dictionary.
        4. Do NOT use print() statements.
        5. Return ONLY the code. No markdown, no explanations.
        
        Example Output:
        result = df['salary'].mean()
        """

    async def analyze_background(self, job_id: str, file_id: str, question: str):
        """
        The main loop: Load -> Think -> Code -> Execute -> Save
        """
        try:
            # 1. Start
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Loading data...", 10)
            file_path = self._get_file_path(file_id)
            
            if not os.path.exists(file_path):
                raise FileNotFoundError("File not found. Please upload again.")
                
            # Load Data
            df = pd.read_parquet(file_path)
            
            # 2. Ask Gemini
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Consulting AI...", 30)
            
            # Prepare schema summary for the AI
            # We map dtypes to simple strings for the prompt
            columns_summary = []
            for col, dtype in df.dtypes.items():
                columns_summary.append(f"- {col} ({dtype})")
            schema_str = "\n".join(columns_summary)
            
            prompt = f"""
            You are a Python Data Analyst. 
            You are given a Pandas DataFrame named 'df'.
            
            Columns:
            {schema_str}
            
            User Question: {question}
            
            Requirements:
            1. Write Python code to answer the question.
            2. ASSIGN the final answer to a variable named 'result'.
            3. Use the 'df' variable directly.
            4. Return ONLY the python code. Do not use Markdown (```).
            """
            
            # Call Gemini (run in thread to not block asyncio)
            response = await asyncio.to_thread(
                self.model.generate_content, 
                prompt
            )
            
            generated_code = response.text
            
            # 3. Sanitize Code (Remove markdown if Gemini adds it)
            cleaned_code = generated_code.replace("```python", "").replace("```", "").strip()
            
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Executing analysis...", 60)
            
            # 4. Secure Execution
            # We create a local scope with 'df' and 'pd' available
            local_vars = {"df": df, "pd": pd}
            
            try:
                exec(cleaned_code, {}, local_vars)
            except Exception as code_error:
                raise ValueError(f"Generated code failed to execute: {code_error}\nCode was: {cleaned_code}")
                
            # 5. Extract Result
            final_answer = local_vars.get("result")
            
            if final_answer is None:
                raise ValueError("The AI code ran but did not assign a 'result' variable.")

            # Format the answer for the UI
            final_answer_str = str(final_answer)
            final_data = None
            
            # If the result is a DataFrame/Series, convert to dict for JSON serialization
            if isinstance(final_answer, (pd.DataFrame, pd.Series)):
                final_data = final_answer.to_dict()
                final_answer_str = "Generated a data table/series (see attached data)."
            
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Finalizing...", 90)

            # 6. Save Success
            result_payload = ChatResult(
                answer=final_answer_str,
                generated_code=cleaned_code,
                data=final_data
            ).model_dump()
            
            await tracker.set_result(job_id, result_payload)

        except Exception as e:
            await tracker.set_error(job_id, str(e))