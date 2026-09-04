#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Terminal colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Flag variables
DO_CLEAN=0
DO_RUN=0

# Parse arguments
if [ "$#" -eq 0 ]; then
    # Default behavior if no flags passed: just run
    DO_RUN=1
else
    while [[ "$#" -gt 0 ]]; do
        case $1 in
            --clean) DO_CLEAN=1 ;;
            --run) DO_RUN=1 ;;
            -h|--help)
                echo "Usage: ./run_pipeline.sh [OPTIONS]"
                echo "Options:"
                echo "  --clean    Remove Neo4j docker volumes and generated CSV files"
                echo "  --run      Execute the migration pipeline"
                echo "  (If no flags are provided, --run is assumed by default)"
                exit 0
                ;;
            *) echo "Unknown parameter passed: $1"; exit 1 ;;
        esac
        shift
    done
fi

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}    Cloud Migration AI Agent Pipeline                 ${NC}"
echo -e "${BLUE}======================================================${NC}\n"

if [ "$DO_CLEAN" -eq 1 ]; then
    echo -e "${YELLOW}🧹 Cleaning up previous state...${NC}"
    # Stop containers and remove volumes (-v)
    docker compose down -v 2>/dev/null || true
    # Remove generated files
    rm -f data/cleaned_samples.csv
    rm -f data/final_migration_plan.csv
    echo -e "${GREEN}✓ Cleanup complete.${NC}\n"
fi

if [ "$DO_RUN" -eq 1 ]; then
    # 1. Environment Setup
    echo -e "${YELLOW}[1/7] Setting up Python virtual environment...${NC}"
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    source venv/bin/activate
    pip install -q -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed.${NC}\n"

    # 2. Database Startup
    echo -e "${YELLOW}[2/7] Starting Neo4j Database (with APOC & GDS)...${NC}"
    docker compose up -d

    echo -e "Waiting for Neo4j to be ready (this can take 30-40 seconds for plugins to load)..."
    for i in {1..30}; do
        if python3 -c "
try:
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password123'))
    driver.verify_connectivity()
    print('Ready')
except Exception:
    exit(1)
" &> /dev/null; then
            echo -e "${GREEN}✓ Neo4j is ready!${NC}\n"
            break
        fi
        echo -n "."
        sleep 2
        if [ "$i" -eq 30 ]; then
            echo -e "\nError: Neo4j did not start in time. Check docker logs."
            exit 1
        fi
    done

    # 3. Data Normalization
    echo -e "${YELLOW}[3/7] Running Module 1: Data Normalization Agent...${NC}"
    python data_agent.py
    echo -e "${GREEN}✓ Cleaned CSV generated.${NC}\n"

    # 4. Graph Ingestion
    echo -e "${YELLOW}[4/7] Running Module 2: Graph Ingestion Agent...${NC}"
    python neo4j_agent.py
    echo -e "${GREEN}✓ Graph populated.${NC}\n"

    # 5. Architecture & Sizing
    echo -e "${YELLOW}[5/7] Running Module 3 & 4: Cloud Selection & Server Sizing...${NC}"
    python cloud_selection_agent.py
    python sizing_agent.py
    echo -e "${GREEN}✓ Architecture decisions saved.${NC}\n"

    # 6. Risk & Wave Planning
    echo -e "${YELLOW}[6/7] Running Module 5 & 6: Risk Analysis & Wave Planning...${NC}"
    python risk_agent.py
    python wave_agent.py
    echo -e "${GREEN}✓ Migration waves generated.${NC}\n"

    # 7. Final Output
    echo -e "${BLUE}======================================================${NC}"
    echo -e "${GREEN}🎉 Pipeline Execution Complete!${NC}"
    echo -e "${BLUE}======================================================${NC}"
    echo -e "Preview of Final Migration Plan (data/final_migration_plan.csv):"
    head -n 10 data/final_migration_plan.csv | column -s, -t

    echo -e "\n${YELLOW}Note:${NC} You can view the full dependency graph by visiting http://localhost:7474 (neo4j / password123)"
    echo -e "To stop the database, run: docker compose down\n"
fi
