# Cloud Migration AI Agent Pipeline

This repository contains a baseline cloud migration planning pipeline. It reads a sample server discovery CSV, normalizes missing fields, loads the environment into Neo4j, selects a target cloud, recommends server sizes, assigns risk scores, and exports a migration wave plan.

## Section 5. Reproducibility and Run Instructions

### Dependencies

Install these system dependencies before running the baseline:

- Python 3.10 or newer
- Docker Desktop, or another Docker runtime with Docker Compose support
- Docker Engine must be running before starting the pipeline

The Python dependencies are listed in `requirements.txt`:

```bash
pandas>=2.0
langchain>=0.3
langchain-openai>=0.3
langchain-core>=0.3
langchain-community>=0.3
neo4j>=5.0
python-dotenv>=1.0
```

The pipeline script creates a local virtual environment named `venv` and installs these packages automatically.

### Required API Keys and Environment Variables

The LangChain agents use the ASU OpenAI-compatible endpoint configured in the Python files:

```text
https://openai.rc.asu.edu/v1
```

To access this endpoint, you must either be connected to the ASU VPN or connected to ASU Wi-Fi. To set up the ASU VPN, follow:

```text
https://docs.rc.asu.edu/sslvpn/
```

Get an API key from:

```text
https://voyager.rc.asu.edu/
```

Set the following environment variable before running the baseline:

```bash
export ASU_RC_API_KEY="your_api_key_here"
```

You can also place the same value in a local `.env` file:

```bash
ASU_RC_API_KEY=your_api_key_here
```

Use `.env.example` as a template for the required variable name.

Do not commit `.env` files or API keys to the repository.

### Input File

The baseline input file is:

```text
data/sample.csv
```

This file contains sample server discovery data, including hostnames, operating systems, allocated CPU/RAM/storage, application names, business tags, and outbound dependencies.

### Exact Command to Run the Baseline

From the repository root, run:

```bash
./run_pipeline.sh --run
```

If the script is not executable on your machine, run:

```bash
chmod +x run_pipeline.sh
./run_pipeline.sh --run
```

Running `./run_pipeline.sh` with no flags is equivalent to `./run_pipeline.sh --run`.

To start from a clean Neo4j database and remove generated CSV outputs, run:

```bash
./run_pipeline.sh --clean --run
```

### What the Command Does

The script performs these steps:

1. Creates and activates a local Python virtual environment in `venv/`.
2. Installs packages from `requirements.txt`.
3. Starts Neo4j 5 with APOC and Graph Data Science plugins using `compose.yml`.
4. Runs `data_agent.py` to create `data/cleaned_samples.csv`.
5. Runs `neo4j_agent.py` to load servers and dependencies into Neo4j.
6. Runs `cloud_selection_agent.py` and `sizing_agent.py` to choose the target cloud and recommend server sizes.
7. Runs `risk_agent.py` and `wave_agent.py` to assign risk scores, generate migration waves, and export the final CSV.

### Output Files

Generated outputs appear in the `data/` directory:

```text
data/cleaned_samples.csv
data/final_migration_plan.csv
```

The main final output is:

```text
data/final_migration_plan.csv
```

The script also prints a preview of the first rows of the final migration plan in the terminal.

### Neo4j Browser

After the pipeline starts Neo4j, you can inspect the graph in a browser:

```text
http://localhost:7474
```

Use these local credentials:

```text
Username: neo4j
Password: password123
```

To stop Neo4j after running the baseline:

```bash
docker compose down
```

To stop Neo4j and delete the database volume:

```bash
docker compose down -v
```

### Running Individual Modules

The recommended baseline command is `./run_pipeline.sh --run`, but modules can also be run individually in this order:

```bash
python data_agent.py
python neo4j_agent.py
python cloud_selection_agent.py
python sizing_agent.py
python risk_agent.py
python wave_agent.py
```

Run these commands only after installing dependencies and starting Neo4j with:

```bash
docker compose up -d
```

### Known Setup Limitations

- Docker Engine must be running before executing the pipeline.
- Ports `7474` and `7687` must be available for Neo4j.
- The configured Neo4j password is hard-coded for local reproducibility in the project files.
- The LLM-based steps require access to the ASU OpenAI-compatible endpoint, which requires ASU VPN or ASU Wi-Fi, and a valid `ASU_RC_API_KEY` from `https://voyager.rc.asu.edu/`.
- The first Neo4j startup may take 30 to 40 seconds while plugins load.
- The baseline is designed for the included sample input file, `data/sample.csv`.
