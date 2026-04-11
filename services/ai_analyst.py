import ast
import asyncio
import builtins
import json
import re
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

from core.logging_config import get_logger

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
    _logger = get_logger("ai_analyst")

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
            self._logger.info("Groq client initialized successfully")
        else:
            self._logger.warning("GROQ_API_KEY is missing in .env — AI features will be unavailable")

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

    def _validate_generated_code(self, code: str, require_table: bool = True) -> None:
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

        if require_table and not has_result_table_assignment:
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

    # ──────────────────────────────────────────────────────────────
    #  Conversation History Helper
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _build_llm_history(history: list[dict]) -> list[dict]:
        """Convert raw history dicts into LLM message format."""
        messages = []
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content.strip():
                messages.append({"role": role, "content": content})
        return messages

    # ──────────────────────────────────────────────────────────────
    #  Phase 1: Query Planning + Clarification Detection
    # ──────────────────────────────────────────────────────────────

    async def _plan_response(self, question: str, schema_str: str, history: list[dict] | None = None) -> dict:
        """
        Ask the LLM to classify the user's question and decide which
        outputs are needed, or whether clarification is required.
        """
        # Build conversation context for the planner
        history_text = ""
        if history:
            turns = []
            for turn in history:
                role_label = "User" if turn.get("role") == "user" else "Assistant"
                turns.append(f"{role_label}: {turn.get('content', '')}")
            history_text = f"\n**Conversation History:**\n" + "\n".join(turns) + "\n"

        plan_prompt = f"""You are a query planner for a data analysis system.
Given a user's question, the dataset schema, and any prior conversation, decide what to do.

**Dataset Columns:**
{schema_str}
{history_text}
**User's Current Question:** {question}

Respond with ONLY a JSON object (no markdown, no explanation):
{{
  "needs_clarification": true/false,
  "clarification_question": "question to ask the user (only if needs_clarification is true)",
  "needs_code": true/false,
  "needs_table": true/false,
  "needs_chart": true/false,
  "reasoning": "brief explanation"
}}

Decision rules:
- "needs_clarification": true if the question is ambiguous or incomplete. Examples: "show me the top items" (top by what metric?), "filter the data" (filter by what?), "compare them" (compare what?). Set false if the question is clear enough to answer, even if imprecise. When there is conversation history, use it to resolve ambiguity before asking for clarification.
- "needs_code": false if the question can be answered from the schema alone (e.g. "what columns exist?"). true if it requires data computation. Ignored if needs_clarification is true.
- "needs_table": true if the user wants to see data rows, rankings, comparisons, or aggregated results.
- "needs_chart": true if the user explicitly asks for a chart/plot/visualization, or if the question involves trends, distributions, or comparisons that benefit from visualization.
"""
        try:
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise query classifier. Output valid JSON only.",
                    },
                    {"role": "user", "content": plan_prompt},
                ],
                model="openai/gpt-oss-120b",
                temperature=0.0,
                max_tokens=200,
                stream=False,
            )

            raw = response.choices[0].message.content or ""
            raw = raw.strip()

            # Try parsing directly
            try:
                plan = json.loads(raw)
            except json.JSONDecodeError:
                # Fallback: extract JSON from markdown fences or surrounding text
                match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
                if match:
                    plan = json.loads(match.group())
                else:
                    raise ValueError("Could not parse plan JSON")

            result = {
                "needs_clarification": bool(plan.get("needs_clarification", False)),
                "clarification_question": plan.get("clarification_question", ""),
                "needs_code": bool(plan.get("needs_code", True)),
                "needs_table": bool(plan.get("needs_table", True)),
                "needs_chart": bool(plan.get("needs_chart", True)),
            }
            self._logger.info(
                "Plan: clarify=%s code=%s table=%s chart=%s — %s",
                result["needs_clarification"], result["needs_code"],
                result["needs_table"], result["needs_chart"],
                plan.get("reasoning", "no reason given"),
            )
            return result

        except Exception as exc:
            self._logger.warning("Planning failed (%s) — defaulting to full output", exc)
            return {
                "needs_clarification": False,
                "clarification_question": "",
                "needs_code": True,
                "needs_table": True,
                "needs_chart": True,
            }

    # ──────────────────────────────────────────────────────────────
    #  Phase 2: Dynamic Code Generation
    # ──────────────────────────────────────────────────────────────

    def _build_code_prompt(
        self, question: str, schema_str: str, plan: dict,
        history: list[dict] | None = None,
    ) -> str:
        """Build the code generation prompt dynamically based on the plan and history."""
        needs_table = plan["needs_table"]
        needs_chart = plan["needs_chart"]

        parts = [
            "You are a Python Data Analyst.",
            "You are given a Pandas DataFrame named 'df'.",
        ]

        if needs_chart:
            parts.append("You are also given Plotly Express as 'px'.")

        parts.append(f"\nColumns:\n{schema_str}")

        # Include conversation history for follow-up context
        if history:
            parts.append("\nConversation History (for context):")
            for turn in history:
                role_label = "User" if turn.get("role") == "user" else "Assistant"
                parts.append(f"{role_label}: {turn.get('content', '')}")

        parts.append(f"\nCurrent Question: {question}")

        requirements = ["\nRequirements:"]

        if needs_table:
            requirements.append("1. Write Python code to answer the question.")
            requirements.append("2. ASSIGN a pandas DataFrame to a variable named 'result_table'.")
        else:
            requirements.append("1. Write Python code to answer the question.")

        if needs_chart:
            requirements.append(
                f"{'3' if needs_table else '2'}. Build a Plotly chart and ASSIGN "
                "JSON output to 'result_chart' using fig.to_json()."
            )

        requirements.append(f"- Use 'df'{' and px' if needs_chart else ''} directly; do not import anything.")

        if needs_table and needs_chart:
            requirements.append("- Assign result_table before chart logic.")
            requirements.append("- If a meaningful chart is not possible, set result_chart = None.")

        requirements.append("- Return ONLY python code. Do not use Markdown (```).")

        parts.extend(requirements)
        return "\n".join(parts)

    # ──────────────────────────────────────────────────────────────
    #  Phase 3: Summarization
    # ──────────────────────────────────────────────────────────────

    async def _summarize_results(
        self,
        question: str,
        schema_str: str,
        table_df: pd.DataFrame | None = None,
        df_sample: pd.DataFrame | None = None,
        history: list[dict] | None = None,
    ) -> str:
        """
        Generate a natural-language summary answering the user's question.
        Uses the result table if available, otherwise falls back to schema + sample data.
        Includes conversation history for follow-up context.
        """
        if table_df is not None and not table_df.empty:
            context = f"**Result Table (first 10 rows):**\n{table_df.head(10).to_markdown()}"
        elif df_sample is not None:
            context = (
                f"**Dataset Schema:**\n{schema_str}\n\n"
                f"**Sample Data (first 5 rows):**\n{df_sample.head(5).to_markdown()}"
            )
        else:
            context = f"**Dataset Schema:**\n{schema_str}"

        # Build conversation context
        history_text = ""
        if history:
            turns = []
            for turn in history:
                role_label = "User" if turn.get("role") == "user" else "Assistant"
                turns.append(f"{role_label}: {turn.get('content', '')}")
            history_text = "\n**Prior Conversation:**\n" + "\n".join(turns) + "\n"

        summary_prompt = f"""You are a Data Analyst presenting results to a business user.
{history_text}
**User's Current Question:** {question}

{context}

Based ONLY on the information above, provide a concise, natural-language answer
to the user's question. Be specific with numbers and insights.
Do not mention code, DataFrames, or technical implementation details.
Keep it to 2-4 sentences."""

        try:
            summary_response = await asyncio.to_thread(
                self.client.chat.completions.create,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You summarize data analysis results in clear, "
                            "non-technical language for business users."
                        ),
                    },
                    {"role": "user", "content": summary_prompt},
                ],
                model="openai/gpt-oss-120b",
                temperature=0.3,
                max_tokens=300,
                stream=False,
            )
            return summary_response.choices[0].message.content or "Analysis complete."
        except Exception as exc:
            self._logger.warning("Summarization failed: %s", exc)
            return "Analysis complete. Please review the data below."

    # ──────────────────────────────────────────────────────────────
    #  Main Orchestrator
    # ──────────────────────────────────────────────────────────────

    async def analyze_background(
        self, job_id: str, file_id: str, question: str,
        history: list[dict] | None = None,
    ):
        """
        3-Phase ReAct Agent with Human-in-the-Loop:
          Phase 0  →  Clarification check (may short-circuit)
          Phase 1  →  Plan (classify query)
          Phase 2  →  Code Generation + Execution (if needed)
          Phase 3  →  Summarization (always)
        """
        history = history or []

        try:
            self._logger.info(
                "Job %s started — file=%s question='%s' history_turns=%d",
                job_id, file_id, question[:80], len(history),
            )

            if self.client is None:
                raise RuntimeError("AI provider is not configured on the server.")

            # ── Load Data ────────────────────────────────────────
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Loading data...", 10)
            file_path = self._get_file_path(file_id)

            if not os.path.exists(file_path):
                raise FileNotFoundError("File not found. Please upload again.")

            df = pd.read_parquet(file_path)
            self._logger.debug("Loaded parquet: %d rows × %d cols", len(df), len(df.columns))

            # Build schema summary (shared across all phases)
            columns_summary = []
            for col, dtype in df.dtypes.items():
                columns_summary.append(f"- {col} ({dtype})")
            schema_str = "\n".join(columns_summary)

            # ── Phase 1: Plan (with clarification detection) ─────
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Planning response...", 20)
            plan = await self._plan_response(question, schema_str, history=history)

            # ── Clarification Short-Circuit ───────────────────────
            if plan["needs_clarification"]:
                clarification_text = (
                    plan.get("clarification_question")
                    or "Could you please clarify your question?"
                )
                self._logger.info("Job %s → clarification requested: %s", job_id, clarification_text)

                result_payload = ChatResult(
                    summary=clarification_text,
                    clarification=clarification_text,
                ).model_dump()

                await tracker.set_result(job_id, result_payload)
                return

            # ── Phase 2: Code Generation + Execution ─────────────
            cleaned_code = None
            final_data = None
            chart_payload = None
            table_df = None

            if plan["needs_code"]:
                await tracker.update_status(job_id, JobStatus.PROCESSING, "Generating analysis code...", 40)

                prompt = self._build_code_prompt(question, schema_str, plan, history=history)

                # Build LLM messages with conversation history for follow-ups
                llm_messages = [
                    {
                        "role": "system",
                        "content": "You are a Python data analyst assistant that writes clean, efficient pandas code.",
                    },
                ]
                llm_messages.extend(self._build_llm_history(history))
                llm_messages.append({"role": "user", "content": prompt})

                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    messages=llm_messages,
                    model="openai/gpt-oss-120b",
                    temperature=0.1,
                    max_tokens=1000,
                    stream=False,
                )

                generated_code = response.choices[0].message.content or ""
                if not generated_code.strip():
                    raise ValueError("AI returned an empty code response.")

                cleaned_code = self._sanitize_generated_code(generated_code)
                self._validate_generated_code(cleaned_code, require_table=plan["needs_table"])

                # ── Execution ────────────────────────────────────
                await tracker.update_status(job_id, JobStatus.PROCESSING, "Executing analysis...", 60)

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
                    self._logger.warning("Code execution error: %s", code_error)

                # Extract table (if planned)
                if plan["needs_table"]:
                    result_table = local_vars.get("result_table")
                    if result_table is not None:
                        table_df = self._coerce_to_dataframe(result_table)
                        final_data = table_df.to_dict(orient="records")
                    elif execution_error is None:
                        self._logger.warning("Code did not produce result_table despite plan requiring it")

                # Extract chart (if planned)
                if plan["needs_chart"]:
                    result_chart = local_vars.get("result_chart")
                    chart_payload = self._normalize_chart_payload(result_chart)
                    if execution_error is not None:
                        chart_payload = None

            # ── Phase 3: Summarization (always) ──────────────────
            await tracker.update_status(job_id, JobStatus.PROCESSING, "Interpreting results...", 80)

            final_summary = await self._summarize_results(
                question=question,
                schema_str=schema_str,
                table_df=table_df,
                df_sample=df if table_df is None else None,
                history=history,
            )

            await tracker.update_status(job_id, JobStatus.PROCESSING, "Finalizing...", 90)

            # ── Save Result ──────────────────────────────────────
            result_payload = ChatResult(
                summary=final_summary,
                generated_code=cleaned_code,
                table=final_data,
                chart=chart_payload,
            ).model_dump()

            await tracker.set_result(job_id, result_payload)

            row_count = len(final_data) if final_data else 0
            has_chart = chart_payload is not None
            self._logger.info(
                "Job %s completed — summary=%dch table=%d rows chart=%s",
                job_id, len(final_summary), row_count, has_chart,
            )

        except Exception as e:
            self._logger.error("Job %s failed: %s", job_id, e, exc_info=True)
            await tracker.set_error(job_id, str(e))

