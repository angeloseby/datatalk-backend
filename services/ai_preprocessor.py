import asyncio
import pandas as pd

from core.logging_config import get_logger
from services.ai_analyst import AIAnalyst, SAFE_BUILTINS

logger = get_logger("ai_preprocessor")


class AIAgenticPreprocessor(AIAnalyst):
    """
    Agentic data preprocessor that uses the LLM to generate
    context-aware Pandas cleaning code, replacing hardcoded rules.
    Inherits AIAnalyst for the Groq client and code sanitization utilities.
    """

    async def agentic_clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Ask the LLM to write cleaning code tailored to the actual data,
        then execute that code in a sandboxed environment.

        Falls back to the original DataFrame if anything goes wrong.
        """
        try:
            if self.client is None:
                logger.warning("AI provider not configured — skipping agentic clean")
                return df

            logger.info("Starting agentic clean on DataFrame (%d rows × %d cols)", len(df), len(df.columns))

            # --- Build a concise data summary for the LLM ---
            dtype_info = df.dtypes.to_string()
            null_counts = df.isnull().sum().to_string()
            unique_counts = df.nunique().to_string()
            sample_rows = df.head(3).to_string()

            prompt = f"""
You are a Data Engineer Agent.
You are given a Pandas DataFrame named `df`.

**DataFrame Summary**
Dtypes:
{dtype_info}

Null counts per column:
{null_counts}

Unique values per column:
{unique_counts}

Sample rows (first 3):
{sample_rows}

**Task**
Write Python/Pandas code to clean this DataFrame. Apply the following strategies:
1. Trim whitespace from string columns and convert blank strings to NaN.
2. Drop exact duplicate rows.
3. For numeric columns with missing values, fill with the median.
4. For categorical/text columns with missing values, fill with "Unknown".
5. Drop columns where more than 90% of values are null.
6. Normalize string columns to consistent casing (title case) where appropriate.

**Rules**
- Do NOT import pandas; it is already available as `pd`.
- Do NOT import any other libraries.
- The input DataFrame is available as `df`.
- Assign the final cleaned DataFrame to a variable named `cleaned_df`.
- Return ONLY executable Python code. No markdown fences, no explanations.
"""

            logger.debug("Sending cleaning prompt to LLM")
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a data engineering assistant that writes clean, "
                            "efficient Pandas code. Output raw Python only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                model="openai/gpt-oss-120b",
                temperature=0.1,
                max_tokens=1000,
                stream=False,
            )

            generated_code = response.choices[0].message.content or ""
            if not generated_code.strip():
                logger.warning("LLM returned empty code — returning original DataFrame")
                return df

            # Sanitize (strip markdown fences / safe imports)
            cleaned_code = self._sanitize_generated_code(generated_code)
            logger.debug("Executing generated cleaning code (%d chars)", len(cleaned_code))

            # --- Execute in a sandboxed environment ---
            global_vars = {"__builtins__": SAFE_BUILTINS, "pd": pd}
            local_vars = {"df": df.copy()}

            exec(cleaned_code, global_vars, local_vars)

            result = local_vars.get("cleaned_df", df)
            if not isinstance(result, pd.DataFrame):
                logger.warning("LLM code did not produce a DataFrame — returning original")
                return df

            logger.info("Agentic clean complete: %d rows × %d cols", len(result), len(result.columns))
            return result

        except Exception as exc:
            logger.error("Agentic clean failed: %s", exc, exc_info=True)
            return df
