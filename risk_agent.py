"""
Module 5 – Risk Analysis Agent
================================
A LangChain-based agent that uses GraphCypherQAChain to dynamically
read server data from Neo4j, analyses legacy OS and compliance tag
risks, and writes risk scores back to the graph.
"""

import json
import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
from langchain_community.graphs import Neo4jGraph
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import Tool, tool
from langchain_openai import ChatOpenAI

# ── Load environment variables ───────────────────────────────────────────────
load_dotenv()

# Neo4j connection settings
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


# ── Tool 1: Database_Reader (LLM-generated Cypher) ──────────────────────────
def _build_cypher_chain():
    """Build and return a GraphCypherQAChain instance."""
    graph = _get_graph()
    llm = _get_llm()
    return GraphCypherQAChain.from_llm(
        llm=llm,
        graph=graph,
        verbose=True,
        allow_dangerous_requests=True,
        
        top_k=100,
    )


def _run_cypher_reader(query: str) -> str:
    """Wrapper that invokes the cypher chain and returns the result string."""
    chain = _build_cypher_chain()
    result = chain.invoke({"query": query})
    return result.get("result", "No answer returned.")


database_reader = Tool(
    name="Database_Reader",
    func=_run_cypher_reader,
    description=(
        "Translates natural language into Cypher queries to read the "
        "Neo4j graph. Use this to find server IDs, OS versions, and tags."
    ),
)


# ── Tool 2: update_risk_scores (deterministic write) ────────────────────────
@tool
def update_risk_scores(risk_updates: list[dict]) -> str:
    """Write risk scores back to Neo4j Server nodes.

    Args:
        risk_updates: A list of dictionaries, each with 'id' (Server_ID)
                      and 'risk' ('High' or 'Low').
                      Example: [{"id": "SRV-001", "risk": "High"}, ...]

    Returns:
        A confirmation string with counts.
    """
    graph = _get_graph()

    graph.query(
        "UNWIND $updates AS update "
        "MATCH (s:Server {id: update.id}) "
        "SET s.risk_score = update.risk",
        params={"updates": risk_updates},
    )

    high = sum(1 for u in risk_updates if u.get("risk") == "High")
    low = sum(1 for u in risk_updates if u.get("risk") == "Low")

    return (
        f"✅ Risk scores updated in Neo4j.\n"
        f"   Total updated : {len(risk_updates)}\n"
        f"   High risk     : {high}\n"
        f"   Low risk      : {low}"
    )


# ── Agent system prompt ─────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are the Security & Risk Analysis Agent.\n\n"
    "Step 1: Use the `Database_Reader` tool to ask for the "
    "'id, os, and business_tags of all servers in the database'.\n"
    "Step 2: Analyze the results. If the OS contains '2008', '5', or "
    "'6.4' (Legacy), OR if the tags contain 'HIPAA', 'PCI', or 'SOX' "
    "(Compliance), assign a risk of 'High'. Otherwise, assign 'Low'.\n"
    "Step 3: Format your findings into a list of dictionaries and use "
    "the `update_risk_scores` tool to save them. Each dictionary must "
    "have keys 'id' and 'risk'. Example: "
    '[{"id": "SRV-001", "risk": "High"}, {"id": "SRV-002", "risk": "Low"}]'
)


# ── LLM & Agent setup ───────────────────────────────────────────────────────
def build_agent():
    """Construct and return the risk analysis agent."""

    llm = _get_llm()
    tools = [database_reader, update_risk_scores]

    agent = create_agent(
        llm,
        tools,
        system_prompt=SystemMessage(content=SYSTEM_PROMPT),
    )
    return agent


# ── Deterministic fallback ──────────────────────────────────────────────────
LEGACY_MARKERS = ("2008", "RHEL 5", "6.4")
COMPLIANCE_TAGS = ("HIPAA", "PCI", "SOX")


def _run_deterministic_fallback():
    """Fallback that performs the risk analysis without the LLM."""
    graph = _get_graph()

    print("\n── Step 1: Fetching servers ──")
    rows = graph.query(
        "MATCH (s:Server) "
        "RETURN s.id AS id, s.os AS os, s.business_tags AS tags "
        "ORDER BY s.id"
    )
    print(f"   Found {len(rows)} servers.")

    print("\n── Step 2: Analysing risk ──")
    updates = []
    for r in rows:
        os_val = str(r.get("os", ""))
        tags_val = str(r.get("tags", ""))
        is_legacy = any(m in os_val for m in LEGACY_MARKERS)
        is_compliance = any(t in tags_val for t in COMPLIANCE_TAGS)
        risk = "High" if (is_legacy or is_compliance) else "Low"
        updates.append({"id": r["id"], "risk": risk})

    high = [u for u in updates if u["risk"] == "High"]
    low = [u for u in updates if u["risk"] == "Low"]
    print(f"   High risk: {len(high)} servers")
    print(f"   Low risk : {len(low)} servers")
    for u in high:
        print(f"     ⚠ {u['id']}")

    print("\n── Step 3: Saving to Neo4j ──")
    result = update_risk_scores.invoke({"risk_updates": updates})
    print(result)


# ── Main entry point ────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        agent = build_agent()
        result = agent.invoke({
            "messages": [
                HumanMessage(
                    content=(
                        "Analyze all servers for legacy and compliance "
                        "risks, then update their risk scores."
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
        print(f"⚠️  Agent invocation failed ({exc}). Running fallback…")
        _run_deterministic_fallback()

