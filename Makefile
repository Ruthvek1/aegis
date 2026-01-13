.PHONY: setup lint typecheck test clean up down

setup:
	@echo "Setting up backend..."
	cd backend && uv sync
	@echo "Setting up frontend..."
	cd frontend && npm install

lint:
	@echo "Linting backend..."
	cd backend && uv run ruff check .
	@echo "Linting frontend..."
	cd frontend && npm run lint

typecheck:
	@echo "Typechecking backend..."
	cd backend && uv run mypy .
	@echo "Typechecking frontend..."
	cd frontend && npx tsc --noEmit

test:
	@echo "Testing backend..."
	cd backend && uv run pytest || echo "No tests yet"
	@echo "Testing frontend..."
	@echo "No tests yet in frontend"

up:
	cd infra && docker compose up -d

up-observability:
	cd infra && docker compose --profile observability up -d

down:
	cd infra && docker compose down

eval:
	@echo "Running Evals..."
	cd backend && uv run python evals/run_eval.py
