"""
Module 2 – Graph Ingestion Agent
==================================
A LangChain-based agent that reads cleaned server discovery data,
creates Server nodes and COMMUNICATES_WITH edges in a Neo4j graph
database.
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

INPUT_CSV = Path("data/cleaned_samples.csv")

# Neo4j connection settings
NEO4J_URL = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password123"

# ── Tool: ingest_graph_data ──────────────────────────────────────────────────
@tool
def ingest_graph_data(input_path: str = str(INPUT_CSV)) -> str:
    """Read cleaned server discovery CSV and ingest it into Neo4j as a
    dependency graph with Server nodes and COMMUNICATES_WITH edges.

    Args:
        input_path: Path to the cleaned discovery CSV
                    (default: data/cleaned_samples.csv).

    Returns:
        A human-readable summary of how many nodes and edges were created.
    """
    input_path = Path(input_path)

    # 1. Validate input ───────────────────────────────────────────────────────
    if not input_path.exists():
        return f"ERROR: Input file '{input_path}' not found."

    df = pd.read_csv(input_path)
    total_rows = len(df)

    # 2. Connect to Neo4j ─────────────────────────────────────────────────────
    graph = Neo4jGraph(
        url=NEO4J_URL,
        username=NEO4J_USER,
        password=NEO4J_PASSWORD,
    )

    # 3. Create uniqueness constraint ─────────────────────────────────────────
    graph.query(
        "CREATE CONSTRAINT IF NOT EXISTS "
        "FOR (s:Server) REQUIRE s.id IS UNIQUE"
    )

    # 4. Create Server nodes ──────────────────────────────────────────────────
    node_count = 0
    for _, row in df.iterrows():
        graph.query(
            """
            MERGE (s:Server {id: $server_id})
            SET s.hostname       = $hostname,
                s.os             = $os,
                s.cpu            = $cpu,
                s.ram            = $ram,
                s.storage        = $storage,
                s.app            = $app,
                s.business_tags  = $tags,
                s.normalized_cpu = $normalized_cpu,
                s.audit_flag     = $audit_flag
            """,
            params={
                "server_id": row["Server_ID"],
                "hostname": row["Hostname"],
                "os": str(row["OS_Version"]),
                "cpu": float(row["Allocated_vCPU"]),
                "ram": float(row["Allocated_RAM_GB"]),
                "storage": float(row["Storage_GB"]),
                "app": str(row["App_Name"]),
                "tags": str(row.get("Business_Tags", "")),
                "normalized_cpu": float(row["Normalized_CPU_Pct"]),
                "audit_flag": bool(row.get("requires_manual_audit", False)),
            },
        )
        node_count += 1

    # 5. Create COMMUNICATES_WITH edges ────────────────────────────────────────
    edge_count = 0
    for _, row in df.iterrows():
        raw_connections = str(row.get("Outbound_Connections", ""))
        if not raw_connections or raw_connections in ("", "nan", "None"):
            continue

        source_id = row["Server_ID"]
        for conn in raw_connections.split("|"):
            parts = conn.strip().split(":")
            if len(parts) != 3:
                continue  # skip malformed entries

            target_id, port, bandwidth = parts
            graph.query(
                """
                MERGE (source:Server {id: $source_id})
                MERGE (target:Server {id: $target_id})
                MERGE (source)-[r:COMMUNICATES_WITH {port: $port,
                                                      bandwidth: $bandwidth}]->(target)
                """,
                params={
                    "source_id": source_id,
                    "target_id": target_id,
                    "port": port,
                    "bandwidth": bandwidth,
                },
            )
            edge_count += 1

    # 6. Refresh schema and build summary ─────────────────────────────────────
    graph.refresh_schema()

    summary = (
        f"✅ Graph Ingestion Complete\n"
        f"   Rows processed        : {total_rows}\n"
        f"   Server nodes created  : {node_count}\n"
        f"   Edges created         : {edge_count}\n"
        f"   Neo4j URL             : {NEO4J_URL}\n"
        f"   Browser               : http://localhost:7474"
    )
    return summary


# ── LLM & Agent setup ───────────────────────────────────────────────────────
def build_agent():
    """Construct and return a LangGraph react agent for graph ingestion."""

    llm = ChatOpenAI(
        base_url="https://openai.rc.asu.edu/v1",
        api_key=os.environ.get("ASU_RC_API_KEY", "not-set"),
        model="qwen3-coder-30b-a3b-instruct",
        temperature=0.0,
    )

    tools = [ingest_graph_data]

    system_message = SystemMessage(
        content=(
            "You are a Cloud Migration assistant responsible for graph "
            "ingestion. Use the available tools to load cleaned server "
            "discovery data into a Neo4j dependency graph."
        )
    )

    agent = create_agent(llm, tools, system_prompt=system_message)
    return agent


# ── Main entry point ────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        agent = build_agent()
        result = agent.invoke({
            "messages": [
                HumanMessage(
                    content=(
                        "Load the cleaned server discovery data from "
                        "'data/cleaned_samples.csv' into the local Neo4j "
                        "database. Create Server nodes and "
                        "COMMUNICATES_WITH edges."
                    )
                )
            ]
        })
        print("\n─── Agent Response ───")
        print(result["messages"][-1].content)
    except Exception as exc:
        print(f"⚠️  Agent invocation failed ({exc}). Running tool directly…")
        direct_result = ingest_graph_data.invoke({
            "input_path": str(INPUT_CSV),
        })
        print(direct_result)

