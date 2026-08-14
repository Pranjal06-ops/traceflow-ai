.PHONY: install seed test evaluate run-backend run-frontend docker-up docker-down

install:
	pip install -r backend/requirements.txt --break-system-packages
	cd frontend && npm install

seed:
	PYTHONPATH=backend python3 scripts/seed_data.py

test:
	cd backend && python3 -m pytest tests/ -v

evaluate:
	PYTHONPATH=backend python3 scripts/run_evaluation.py

run-backend:
	PYTHONPATH=backend uvicorn app.main:app --reload --app-dir backend --port 8000

run-frontend:
	cd frontend && npm run dev

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v
