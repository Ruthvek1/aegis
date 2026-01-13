# Aegis Multi-Agent Orchestration Framework

Aegis is a production-grade multi-agent orchestration framework, featuring a team of specialized LLM agents (Planner, Researcher, Coder, Critic, Synthesizer) coordinated by a supervisor. It includes shared memory, MCP tools, full observability, evals, cost control, and a live web UI.

## Getting Started

1. Set up the local environment:

```bash
make setup
```

2. Start the infrastructure (Postgres + pgvector):

```bash
make up
```

_(Optional) Start with Langfuse observability:_

```bash
make up-observability
```

3. Copy the environment variables:

```bash
cp .env.example .env
```

## Architecture

(More details to come in later phases)
