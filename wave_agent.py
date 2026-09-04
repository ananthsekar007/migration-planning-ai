"""
Module 6 – Wave Planning Agent
================================
A LangChain-based agent that uses Neo4j Graph Data Science (GDS) to
group servers into affinity waves, and exports the final schedule to CSV.
"""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_community.graphs import Neo4jGraph
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# ── Load environment variables ───────────────────────────────────────────────
load_dotenv()

NEO4J_URL = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password123"

# ── Shared resources ────────────────────────────────────────────────────────
def _get_graph() -> Neo4jGraph:
    """Return a Neo4jGraph instance."""
    return Neo4jGraph(
        url=NEO4J_URL,
        username=NEO4J_USER,
        password=NEO4J_PASSWORD,
    )

def _get_llm() -> ChatOpenAI:
    """Return a ChatOpenAI instance pointing to the ASU Voyager endpoint."""
    return ChatOpenAI(
        base_url="https://openai.rc.asu.edu/v1",
        api_key=os.environ.get("ASU_RC_API_KEY", "not-set"),
        model="qwen3-coder-30b-a3b-instruct",
        temperature=0.0,
    )

# ── Tool 1: generate_migration_waves ─────────────────────────────────────────
@tool
def generate_migration_waves() -> str:
    """Group connected servers into affinity waves using Graph Data Science.

    Returns:
        A string indicating how many unique migration waves were created.
    """
    graph = _get_graph()

    # 1. Clean up any existing projection
    try:
        graph.query("CALL gds.graph.drop('migrationGraph')")
    except Exception:
        pass

    # 2. Project the graph
    graph.query(
        "CALL gds.graph.project("
        "'migrationGraph', "
        "'Server', "
        "'COMMUNICATES_WITH'"
        ")"
    )

    # 3. Run WCC to identify independent components (waves)
    wcc_results = graph.query(
        "CALL gds.wcc.write('migrationGraph', { writeProperty: 'wave_id' }) "
        "YIELD componentCount"
    )
    component_count = wcc_results[0].get("componentCount", 0) if wcc_results else 0

    # 4. Cleanup projection
    graph.query("CALL gds.graph.drop('migrationGraph')")

    return f"Successfully grouped servers into {component_count} dependency waves."

# ── Tool 2: export_migration_plan ────────────────────────────────────────────
@tool
def export_migration_plan() -> str:
    """Export the final migration plan to a CSV file.

    Returns:
        A string confirming the save location.
    """
    graph = _get_graph()

    results = graph.query(
        "MATCH (s:Server) "
        "RETURN s.id as Server_ID, s.hostname as Hostname, s.os as OS, "
        "s.normalized_cpu as Normalized_CPU, s.target_size as Target_Size, "
        "s.risk_score as Risk_Score, s.wave_id as Wave_ID "
        "ORDER BY s.wave_id, s.id"
    )

    if not results:
        return "ERROR: No server data found to export."

    df = pd.DataFrame(results)
    out_path = Path("data/final_migration_plan.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    return f"Final migration plan exported to {out_path.absolute()}"

# ── Agent system prompt ─────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are the Orchestration Agent.\n"
    "Step 1: Use the `generate_migration_waves` tool to group all "
    "connected servers into affinity waves.\n"
    "Step 2: WAIT for Step 1 to finish completely, then use the `export_migration_plan` "
    "tool to save the final database state to a CSV file."
)

# ── LLM & Agent setup ───────────────────────────────────────────────────────
def build_agent():
    """Construct and return the wave planning agent."""
    llm = _get_llm()
    tools = [generate_migration_waves, export_migration_plan]

    agent = create_agent(
        llm,
        tools,
        system_prompt=SystemMessage(content=SYSTEM_PROMPT),
    )
    return agent

# ── Main entry point ────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        agent = build_agent()
        result = agent.invoke({
            "messages": [
                HumanMessage(
                    content=(
                        "Group the servers into dependency waves and "
                        "export the final migration schedule."
                    )
                )
            ]
        })
        print("\n─── Agent Response ───")
        for msg in result["messages"]:
            role = getattr(msg, "type", "unknown")
            if hasattr(msg, "content") and msg.content:
                print(f"\n[{role}] {msg.content}")
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    print(f"\n[tool_call] {tc['name']}({tc['args']})")
    except Exception as exc:
        print(f"⚠️  Agent invocation failed ({exc}). Running tools directly…")
        print("\n── Step 1: Generate Waves ──")
        print(generate_migration_waves.invoke({}))
        print("\n── Step 2: Export Plan ──")
        print(export_migration_plan.invoke({}))
