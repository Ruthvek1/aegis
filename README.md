<div align="center">
  <h1>AEGIS (AI-Enhanced Guardian & Intelligence System)</h1>
  <p><strong>A Highly Reliable, Graph-Based Orchestration Framework for Agentic Software Engineering</strong></p>
  
  <br />

  [![Python](https://img.shields.io/badge/Python-3.11-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
  [![React](https://img.shields.io/badge/React-18-61DAFB.svg?style=for-the-badge&logo=react&logoColor=black)](https://reactjs.org)
  [![Tailwind CSS](https://img.shields.io/badge/Tailwind-3.4-38B2AC.svg?style=for-the-badge&logo=tailwind-css&logoColor=white)](https://tailwindcss.com)
  [![LangGraph](https://img.shields.io/badge/LangGraph-Supported-000000.svg?style=for-the-badge&logo=langchain&logoColor=white)](https://langchain.com)
  [![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com)
  [![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)
</div>

<br />

### 📸 Application Interface
<div align="center">
  <img src="assets/dashboard.png" width="48%" alt="System Dashboard" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);" />
  <img src="assets/run.png" width="48%" alt="Live Agent Run" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);" />
</div>

<br />

## 📖 Table of Contents

- [Overview & Motivation](#-overview--motivation)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Core Technologies](#-core-technologies)
- [Detailed Workflows](#-detailed-workflows)
  - [Agentic Graph Execution Flow](#1-agentic-graph-execution-flow)
  - [Dockerized Sandboxing](#2-dockerized-sandboxing)
  - [Memory & Persistence Layer](#3-memory--persistence-layer)
- [Observability & Telemetry](#-observability--telemetry)
- [Safety & Guardrails](#-safety--guardrails)
- [Repository Structure](#-repository-structure)
- [Quick Start Deployment](#-quick-start-deployment)
- [Contributing](#-contributing)

---

## 🎯 Overview & Motivation

**AEGIS** is an advanced Multi-Agent coding framework explicitly designed to solve the reliability, safety, and traceability challenges in autonomous software engineering. 

While most agentic frameworks (like AutoGPT or standard sequential chains) hallucinate uncontrollably or cause destructive environment modifications, AEGIS introduces a **Graph-based State Machine (via LangGraph)** coupled with **Strict Docker Sandboxing**. This ensures that agents can plan, code, test, and critically evaluate their own work before any code reaches a production environment.

By implementing specialized autonomous agents (Planner, Coder, Critic, Researcher, Synthesizer) supervised by a central routing intelligence, AEGIS operates reliably at scale while adhering to strict financial limits (Hard-Cap Budgets) and semantic memory constraints.

---

## ✨ Key Features

- **Multi-Agent DAG Architecture:** State transitions are strictly governed by a directed acyclic graph built on LangGraph. Agents cannot loop infinitely without supervision.
- **Dockerized Code Execution:** The `Coder` agent executes all arbitrary LLM-generated code in a tightly restricted Alpine Linux Docker container, completely isolated from the host OS.
- **Self-Correction & Veto Gates:** The `Critic` agent evaluates test outcomes against requirements. If a test fails, the Critic forces the Coder into a self-correction loop.
- **Persistent Episodic & Semantic Memory:** Powered by PostgreSQL and `pgvector`, the memory manager distills "lessons learned" and semantic relationships to avoid repeating past mistakes across runs.
- **Mock/Cassette Replay System:** Deterministic end-to-end testing achieved via `CassetteChatModel`, completely eliminating flakiness and cost during CI testing.
- **Live Streaming Frontend:** A modern React + Zustand frontend utilizing Server-Sent Events (SSE) to render agent interactions, thoughts, and telemetry live.
- **Hard-Cap Budgeting:** Real-time token tracking via OpenTelemetry ensures autonomous runs are instantly killed if they exceed user-defined $ limits.
- **Power Toggles:** Select between high-performance (70B) and cost-effective (8B) Llama 3.1 LLMs dynamically via the UI to respect rate limits on free-tier APIs.

---

## 🏗 System Architecture

AEGIS employs a decoupled Control Plane (Backend API) and Data Plane (Frontend/SSE) model.

```mermaid
graph TD
    %% Styling Classes
    classDef client fill:#3b82f6,stroke:#1d4ed8,stroke-width:2px,color:#fff,rx:8px,ry:8px
    classDef frontend fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff,rx:8px,ry:8px
    classDef backend fill:#f59e0b,stroke:#b45309,stroke-width:2px,color:#fff,rx:8px,ry:8px
    classDef db fill:#6366f1,stroke:#4338ca,stroke-width:2px,color:#fff,rx:8px,ry:8px
    classDef ai fill:#ec4899,stroke:#be185d,stroke-width:2px,color:#fff,rx:8px,ry:8px
    classDef worker fill:#8b5cf6,stroke:#6d28d9,stroke-width:2px,color:#fff,rx:8px,ry:8px

    %% Users
    U[👥 Developer / User]:::client -->|React / Vite| N[⚛️ Frontend UI]:::frontend
    
    %% Frontend
    subgraph Frontend [Presentation Layer]
        N -->|REST / SSE| API[⚡ FastAPI Backend]:::backend
    end

    %% Backend Core
    subgraph Backend [AEGIS Control Plane]
        API -->|Instantiate| Graph[🕸️ LangGraph State Machine]:::backend
        
        Graph -->|Read/Write State| DB[(🐘 PostgreSQL Checkpointer)]:::db
        Graph -->|Vector Search| DB
        
        Graph -->|Tool Calling| Sandbox[🐳 Docker Sandbox]:::worker
    end

    %% AI Integrations
    subgraph AI Layer
        Graph -->|LLM Abstraction| LLM[🧠 ChatOpenAI API <br/> NVIDIA Llama 3.1]:::ai
        LLM -.->|Mock| Cassettes[📼 JSON Cassettes]:::db
    end
```

> **Architecture Overview:** The React frontend streams live execution state using Server-Sent Events from the FastAPI backend. The Backend builds a stateful LangGraph of specialized agents, persisting checkpoints directly to PostgreSQL. The AI layer leverages NVIDIA's API for Llama 3.1 (70B/8B) but falls back gracefully to `Cassette` replays in testing environments.

---

## 💻 Core Technologies

<details>
<summary><strong>Frontend Stack</strong></summary>

- **React 18 & Vite:** Lightning fast HMR and compilation.
- **Zustand:** Highly performant, unopinionated state management for the event stream.
- **Tailwind CSS & Lucide React:** Rapid, consistent UI styling and iconography.
- **SSE Client (`@microsoft/fetch-event-source`):** Reliable Server-Sent Event consumption.
</details>

<details>
<summary><strong>Backend Stack</strong></summary>

- **FastAPI:** Asynchronous API routing and dependency injection.
- **LangGraph & LangChain:** Core multi-agent state machine and LLM abstractions.
- **PostgreSQL & psycopg_pool:** Async connection pooling for memory and graph checkpointing.
- **Docker SDK:** Secure arbitrary code execution via `run_in_sandbox`.
- **OpenTelemetry:** Granular tracing and real-time token/cost accounting.
</details>

---

## 🔍 Detailed Workflows

### 1. Agentic Graph Execution Flow
AEGIS does not use sequential chaining. It uses a **Supervisor** node that dynamically routes execution based on the current state and classification of the task (e.g. SNIPPET, PROJECT, CHAT).
1. **Supervisor** inspects the input and delegates to the **Planner** (for complex tasks) or lightweight nodes (for chat/snippets).
2. **Planner** queries Semantic Memory to construct an execution plan.
3. **Coder** executes the plan, interacting with the file system exclusively inside the isolated Docker sandbox.
4. **Critic** reviews the Docker exit codes and standard out. If a test fails, it routes back to Coder with error context.
5. **Synthesizer** aggregates the successful output, logs it to Episodic Memory, and streams the final payload to the client.

### 2. Dockerized Sandboxing
Safety is paramount. The `sandbox.py` module automatically spins up a lightweight Alpine container for the `Coder` node.
- Host directories are mounted as Read/Write exclusively within a tightly scoped `/workspace` mount.
- Container execution is heavily restricted with hard-timeouts and no root privileges.
- Network isolation ensures the LLM-generated code cannot make unauthorized outbound requests.

### 3. Memory & Persistence Layer
- **Episodic Memory:** Stores "Run Summaries" (what was asked, what was planned, what was achieved).
- **Procedural Memory:** Distilled skills and tool-call sequences stored for future runs.
- **Semantic Memory:** Extracted Entity-Relationship mappings (e.g. `Server.py -> DependsOn -> Graph.py`) embedded via `pgvector` for intelligent context retrieval.

---

## 📊 Observability & Telemetry

AEGIS features deep instrumentation via **OpenTelemetry**. Every node invocation, LLM call, and tool execution is wrapped in a discrete span. 
- Real-time token usage is parsed from the LLM `response_metadata`.
- Exact dollar costs are calculated incrementally and pushed to the frontend via the SSE `usage` event stream.
- Execution halts instantly if the cumulative cost span exceeds the `max_cost_usd` defined in the request payload.

---

## 🛡️ Safety & Guardrails

We believe AI systems should be inherently safe and deterministic. AEGIS implements strict guardrails:
1. **Prompt Injection Detection:** The Critic Node cross-references user inputs with standard prompt injection heuristics. If detected, the run is immediately vetoed.
2. **Red-Green-Refactor Checks:** For flagship engineering tasks, AEGIS enforces that a failing test must be proven (Red) before the Coder is allowed to submit a fix (Green).
3. **Infinite Loop Protection:** Hard-capped iteration limits and financial budget constraints kill the LangGraph state machine before it spirals out of control.

---

## 📂 Repository Structure

```text
AEGIS/
├── backend/
│   ├── aegis/
│   │   ├── agents.py       # LangGraph Node Implementations
│   │   ├── graph.py        # DAG Routing Logic
│   │   ├── memory.py       # Async Postgres & pgvector Interface
│   │   ├── sandbox.py      # Docker SDK integration
│   │   ├── server.py       # FastAPI & SSE implementation
│   │   └── telemetry.py    # OpenTelemetry & Cost Tracking
│   ├── tests/              # Extensive Pytest suite
│   └── cassettes/          # Replay JSONs for deterministic CI
├── frontend/
│   ├── src/
│   │   ├── components/     # React UI Components (TopBar, TranscriptPane)
│   │   ├── store.ts        # Zustand State Management
│   │   └── App.tsx         # Main View Layout
│   └── index.html
└── AEGIS_BUILD_PROMPT.md   # The master specification document
```

---

## 🚀 Quick Start Deployment

1. **Clone the Repository**
```bash
git clone https://github.com/Ruthvek1/aegis.git
cd aegis
```

2. **Backend Setup**
```bash
cd backend
uv sync
cp ../.env.example ../.env
# Edit .env and add your NVIDIA_API_KEY_1
uv run uvicorn aegis.server:app --reload
```

3. **Frontend Setup**
```bash
cd ../frontend
npm install
npm run dev
```

4. **Run the Application**
Open `http://localhost:5173` in your browser. Choose between **Replay Mode** (Free, deterministic) or **BYO Key Mode** (Live LLM execution).

---

## 🤝 Contributing
Contributions are welcome! If you're interested in expanding the capabilities of AEGIS (e.g., adding more specialized agents, supporting new LLM providers, or enhancing the frontend UI), please open an issue or submit a PR. 

All PRs must pass the Github Actions CI pipeline, which runs the deterministic test suite via `pytest` and `uv`!
