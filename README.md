# Project Hub

A project management API: create projects, attach PDF/DOCX documents to
them, and share access with other users. Built around an async FastAPI
service, S3-backed file storage, and a Lambda that keeps per-project storage
usage in sync.

## Stack

- Python 3.10, FastAPI, Pydantic v2
- PostgreSQL via SQLAlchemy 2.0 (async, `asyncpg`), Alembic for migrations
- AWS S3 for document storage, AWS Lambda for S3-event-triggered size recalculation
- LocalStack stands in for S3 and Lambda locally
- Docker Compose for local dev, GitHub Actions for CI

## Getting started

```bash
cp .env.example .env
docker compose up --build
```

| | |
|---|---|
| API | http://localhost:8000 |
| Interactive docs | http://localhost:8000/docs |
| Liveness | http://localhost:8000/health |
| Readiness (checks Postgres) | http://localhost:8000/health/db |

## Useful commands

| Command | Description |
|---|---|
| `docker compose logs -f api` | Tail application logs |
| `docker compose exec api bash` | Shell into the API container |
| `docker compose exec api pytest` | Run the test suite |
| `docker compose exec api ruff check .` | Lint |
| `docker compose exec db psql -U app projects` | Open a psql shell |
| `docker compose down -v` | Stop the stack and wipe the database volume |
