import ast
import asyncio
import builtins
import json
import os
from pathlib import Path
from tempfile import gettempdir
import numpy as np
import pandas as pd
import plotly.express as px
from groq import Groq
from core.status_tracker import tracker, JobStatus
from schemas.chat import ChatResult
from config.settings import settings

SAFE_BUILTINS = {
    "abs": builtins.abs,
    "all": builtins.all,
    "any": builtins.any,
    "bool": builtins.bool,
    "dict": builtins.dict,
    "enumerate": builtins.enumerate,
    "float": builtins.float,
    "int": builtins.int,
    "isinstance": builtins.isinstance,
    "len": builtins.len,
    "list": builtins.list,
    "max": builtins.max,
    "min": builtins.min,
    "range": builtins.range,
    "round": builtins.round,
    "set": builtins.set,
    "sorted": builtins.sorted,
    "str": builtins.str,
    "sum": builtins.sum,
    "tuple": builtins.tuple,
    "zip": builtins.zip,
}

class AIAnalyst:
    SAFE_IMPORT_LINES = {
        "import plotly.express as px",
        "from plotly import express as px",
        "import json",
    }
    FORBIDDEN_NODE_TYPES = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Lambda,
        ast.With,
        ast.AsyncWith,
        ast.While,
        ast.For,
        ast.AsyncFor,
        ast.Try,
        ast.Raise,
        ast.Global,
        ast.Nonlocal,
        ast.Delete,
    )
    FORBIDDEN_CALLS = {
        "compile",
        "delattr",
        "eval",
        "exec",
        "getattr",
        "globals",
        "input",
        "locals",
        "open",
        "setattr",
        "__import__",
    }
    FORBIDDEN_ROOT_NAMES = {
        "builtins",
        "os",
        "pathlib",
        "requests",
        "shutil",
        "socket",
        "subprocess",
        "sys",
    }

    def __init__(self):
        self.processed_dir = Path(gettempdir()) / "datatalk_backend" / "processed"
        self.client = None
        
        # Configure Groq
        if settings.ai.groq_api_key:
            self.client = Groq(api_key=settings.ai.groq_api_key)
        else:
            print("WARNING: GROQ_API_KEY is missing in .env")

    def _get_file_path(self, file_id: str) -> str:
        return str(self.processed_dir / f"{file_id}.parquet")

    def _get_call_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent_name = self._get_call_name(node.value)
            if parent_name:
                return f"{parent_name}.{node.attr}"
            return node.attr
        return None

    def _sanitize_generated_code(self, code: str) -> str:
        sanitized = code.replace("```python", "").replace("```", "").strip()
        if not sanitized:
            return sanitized

        filtered_lines = []
        for line in sanitized.splitlines():
            if line.strip() in self.SAFE_IMPORT_LINES:
                continue
            filtered_lines.append(line)
        return "\n".join(filtered_lines).strip()

    def _validate_generated_code(self, code: str) -> None:
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as exc:
            raise ValueError(f"Generated code has invalid syntax: {exc.msg}") from exc

        has_result_table_assignment = False
        for node in ast.walk(tree):
            if isinstance(node, self.FORBIDDEN_NODE_TYPES):
                raise ValueError("Generated code contains forbidden Python constructs.")

            if isinstance(node, (ast.Import, ast.ImportFrom)):
                raise ValueError("Generated code contains forbidden imports.")

            if isinstance(node, ast.Name) and node.id.startswith("__"):
                raise ValueError("Generated code contains restricted names.")

            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                raise ValueError("Generated code contains restricted attribute access.")

            if isinstance(node, ast.Assign):
                if any(isinstance(target, ast.Name) and target.id == "result_table" for target in node.targets):
                    has_result_table_assignment = True
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "result_table":
                    has_result_table_assignment = True

            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node.func)
                if call_name:
                    root = call_name.split(".")[0]
                    if root in self.FORBIDDEN_ROOT_NAMES or call_name in self.FORBIDDEN_CALLS:
                        raise ValueError("Generated code attempted restricted operations.")

        if not has_result_table_assignment:
            raise ValueError("Generated code must assign the final value to a 'result_table' variable.")

    def _coerce_to_dataframe(self, value: object) -> pd.DataFrame:
        if isinstance(value, pd.DataFrame):
            return value
        if isinstance(value, pd.Series):
            name = value.name if value.name is not None else "value"
            return value.to_frame(name=name)
        if isinstance(value, dict):
            try:
                return pd.DataFrame(value)
            except ValueError:
                return pd.DataFrame([value])
        if isinstance(value, list):
            return pd.DataFrame(value)
        if np.isscalar(value):
            return pd.DataFrame([{"value": value}])
        try:
            return pd.DataFrame(value)
        except Exception as exc:
            raise ValueError("result_table must be convertible to a pandas DataFrame.") from exc

    def _normalize_chart_payload(self, chart_value: object) -> dict | None:
        if chart_value is None:
            return None

        if isinstance(chart_value, dict):
            return chart_value

        if isinstance(chart_value, str):
            stripped_chart = chart_value.strip()
            if not stripped_chart:
                return None
            try:
                parsed = json.loads(stripped_chart)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None

        if hasattr(chart_value, "to_json"):
            try:
                parsed = json.loads(chart_value.to_json())
            except Exception:
                return None
            return parsed if isinstance(parsed, dict) else None

        return None

    async def analyze_background(self, job_id: str, file_id: str, question: str):
        """
        The main loop: Load -> Think -> Code -> Execute -> Save
        """
        try:
            if self.client is None:
                raise RuntimeError("AI provider is not configured on the server.")

            # 1. Start
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Loading data...", 10)
            file_path = self._get_file_path(file_id)
            
            if not os.path.exists(file_path):
                raise FileNotFoundError("File not found. Please upload again.")
                
            # Load Data
            df = pd.read_parquet(file_path)
            
            # 2. Ask Grok
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Consulting AI...", 30)
            
            # Prepare schema summary for the AI
            columns_summary = []
            for col, dtype in df.dtypes.items():
                columns_summary.append(f"- {col} ({dtype})")
            schema_str = "\n".join(columns_summary)
            
            prompt = f"""
            You are a Python Data Analyst. 
            You are given a Pandas DataFrame named 'df'.
            You are also given Plotly Express as 'px'.
            
            Columns:
            {schema_str}
            
            User Question: {question}
            
            Requirements:
            1. Write Python code to answer the question.
            2. ASSIGN a pandas DataFrame to a variable named 'result_table'.
            3. Build a Plotly chart and ASSIGN JSON output to 'result_chart' using fig.to_json().
            4. Use 'df' and 'px' directly; do not import anything.
            5. Assign result_table before chart logic.
            6. If a meaningful chart is not possible, set result_chart = None.
            7. Return ONLY python code. Do not use Markdown (```).
            """
            
            # Call Grok (run in thread to not block asyncio)
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a Python data analyst assistant that writes clean, efficient pandas code."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model="openai/gpt-oss-120b",  # Or "llama3-70b-8192", "llama3-8b-8192", "gemma2-9b-it"
                temperature=0.1,
                max_tokens=1000,
                stream=False
            )
            
            generated_code = response.choices[0].message.content or ""
            if not generated_code.strip():
                raise ValueError("AI returned an empty code response.")
            
            # 3. Sanitize Code (Remove markdown if Grok adds it)
            cleaned_code = self._sanitize_generated_code(generated_code)
            self._validate_generated_code(cleaned_code)
            
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Executing analysis...", 60)
            
            # 4. Secure Execution
            global_vars = {
                "__builtins__": SAFE_BUILTINS,
                "pd": pd,
                "np": np,
                "px": px,
                "json": json,
            }
            local_vars = {"df": df}
            
            execution_error = None
            try:
                exec(cleaned_code, global_vars, local_vars)
            except Exception as code_error:
                execution_error = code_error

            # 5. Extract table and chart results (table is required, chart is optional)
            result_table = local_vars.get("result_table")
            if result_table is None:
                raise ValueError(
                    "The AI code did not assign 'result_table'."
                    + (
                        f" Execution error: {execution_error}"
                        if execution_error
                        else ""
                    )
                )

            table_df = self._coerce_to_dataframe(result_table)
            final_data = table_df.to_dict(orient="records")

            result_chart = local_vars.get("result_chart")
            chart_payload = self._normalize_chart_payload(result_chart)

            if execution_error is not None:
                chart_payload = None

            final_answer_str = "Generated a data table and chart."
            if chart_payload is None:
                if execution_error is not None:
                    final_answer_str = "Generated a data table. Chart generation failed, so chart was omitted."
                else:
                    final_answer_str = "Generated a data table. No chart was returned."
            
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Finalizing...", 90)

            # 6. Save Success
            result_payload = ChatResult(
                answer=final_answer_str,
                generated_code=cleaned_code,
                data=final_data,
                chart=chart_payload,
            ).model_dump()
            
            await tracker.set_result(job_id, result_payload)

        except Exception as e:
            await tracker.set_error(job_id, str(e))
