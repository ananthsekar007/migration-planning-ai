"""
Module 1 – Data Normalization Agent
=====================================
A LangChain-based agent that reads raw server discovery data,
flags missing values, imputes safe defaults, computes a normalized
CPU metric, and persists the cleaned result.
"""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

# ── Load environment variables ───────────────────────────────────────────────
load_dotenv()

# ── Safe defaults for imputation ─────────────────────────────────────────────
DEFAULTS = {
    "OS_Version": "Unknown Legacy OS",
    "Allocated_vCPU": 2,
    "Allocated_RAM_GB": 4,
    "Storage_GB": 50,
    "Peak_CPU_Pct": 20,
    "Avg_CPU_Pct": 5,
}

INPUT_CSV = Path("data/sample.csv")
OUTPUT_CSV = Path("data/cleaned_samples.csv")


# ── Tool: clean_discovery_data ───────────────────────────────────────────────
@tool
def clean_discovery_data(input_path: str = str(INPUT_CSV),
                         output_path: str = str(OUTPUT_CSV)) -> str:
    """Read raw server discovery CSV, flag & impute missing values,
    compute Normalized_CPU_Pct, and save the cleaned result.

    Args:
        input_path:  Path to the raw discovery CSV (default: data/sample.csv).
        output_path: Path where the cleaned CSV will be saved
                     (default: data/cleaned_samples.csv).

    Returns:
        A human-readable summary of what was processed.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    # 1. Read the CSV ─────────────────────────────────────────────────────────
    if not input_path.exists():
        return f"ERROR: Input file '{input_path}' not found."

    df = pd.read_csv(input_path)
    total_rows = len(df)

    # 2. Flag rows missing critical compute metrics ───────────────────────────
    critical_cols = ["Allocated_vCPU", "Allocated_RAM_GB", "Storage_GB", "OS_Version"]
    df["requires_manual_audit"] = df[critical_cols].isna().any(axis=1)
    flagged_count = int(df["requires_manual_audit"].sum())

    # 3. Impute missing values with safe defaults ─────────────────────────────
    imputation_report: dict[str, int] = {}
    for col, default in DEFAULTS.items():
        missing_before = int(df[col].isna().sum())
        if missing_before > 0:
            df[col] = df[col].fillna(default)
            imputation_report[col] = missing_before

    # 4. Calculate Normalized_CPU_Pct ─────────────────────────────────────────
    df["Normalized_CPU_Pct"] = (
        df["Peak_CPU_Pct"].astype(float) * 0.70
        + df["Avg_CPU_Pct"].astype(float) * 0.30
    ).round(2)

    # 5. Save cleaned output ──────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    # 6. Build summary ────────────────────────────────────────────────────────
    imp_lines = "\n".join(
        f"  • {col}: {cnt} missing → filled with '{DEFAULTS[col]}'"
        for col, cnt in imputation_report.items()
    )
    summary = (
        f"✅ Data Normalization Complete\n"
        f"   Rows processed : {total_rows}\n"
        f"   Rows flagged   : {flagged_count}\n"
        f"   Imputed fields :\n{imp_lines}\n"
        f"   Output saved to: {output_path}"
    )
    return summary


# ── LLM & Agent setup ───────────────────────────────────────────────────────
def build_agent():
    """Construct and return a LangGraph react agent."""

    llm = ChatOpenAI(
        base_url="https://openai.rc.asu.edu/v1",
        api_key=os.environ.get("ASU_RC_API_KEY", "not-set"),
        model="qwen3-coder-30b-a3b-instruct",
        temperature=0.0,
    )

    tools = [clean_discovery_data]

    system_message = SystemMessage(
        content=(
            "You are a Cloud Migration assistant responsible for data "
            "normalization. Use the available tools to clean and prepare "
            "server discovery data for migration planning."
        )
    )

    agent = create_agent(llm, tools, system_prompt=system_message)
    return agent


# ── Main entry point ────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Try running through the agent; fall back to direct tool call if the
    # LLM endpoint is unreachable (e.g. missing API key during local dev).
    try:
        agent = build_agent()
        result = agent.invoke({
            "messages": [
                HumanMessage(
                    content=(
                        "Clean the server discovery data in 'data/sample.csv'. "
                        "Flag any rows with missing critical compute metrics, "
                        "impute safe defaults, compute the Normalized_CPU_Pct, "
                        "and save the result to 'data/cleaned_samples.csv'."
                    )
                )
            ]
        })
        print("\n─── Agent Response ───")
        # The last message in the result contains the agent's final answer.
        print(result["messages"][-1].content)
    except Exception as exc:
        print(f"⚠️  Agent invocation failed ({exc}). Running tool directly…")
        direct_result = clean_discovery_data.invoke({
            "input_path": str(INPUT_CSV),
            "output_path": str(OUTPUT_CSV),
        })
        print(direct_result)

