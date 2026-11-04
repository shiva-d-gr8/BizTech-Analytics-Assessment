# Biz-Tech Analytics Assessment

## Overview

This repository contains a Django application developed in response to a
full-stack developer assessment. It includes an asynchronous email queue
implemented with Celery and Redis, a Redis-backed sliding-window rate limiter,
and an order-summary API that demonstrates Django ORM optimization.

## Requirements

- Python 3.12
- A running Redis-compatible server (Redis or Memurai on Windows)
- Git

## Local setup

With Python and Redis already installed, setup and the full test suite should
take less than five minutes. The queue tests use a separate Redis database
(`/1`) and start their own Celery worker; they do not send real email.
Run the commands below from the repository root, the folder containing
`manage.py`.

### Windows (PowerShell)

From the project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start Redis or the Memurai service, then confirm the default Redis connection:

```powershell
python -c "import redis; print(redis.Redis.from_url('redis://localhost:6379/0').ping())"
```

The command should print `True`. Apply migrations, run checks and tests, then
start Django:

```powershell
python manage.py migrate
python manage.py check
pytest -q
python manage.py runserver
```

On Windows, install a Redis-compatible service such as
[Memurai Developer](https://www.memurai.com/get-memurai) if Redis is not
already available. Start the Memurai service before running the Redis check
and tests.

### macOS or Linux

Create and activate a virtual environment, install dependencies, and start a
local Redis server using your operating system's package manager. Then run:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -c "import redis; print(redis.Redis.from_url('redis://localhost:6379/0').ping())"
python manage.py migrate
python manage.py check
pytest -q
python manage.py runserver
```

The test suite takes about two minutes on the assessment development setup.
Keep the development server running while using the app.

## Email worker

Start a Celery worker in a separate terminal after Redis is running:

```bash
celery -A config worker --loglevel=info --pool=solo
```

The configured development email backend prints sent messages to the
terminal. The queue tests start their own worker and use the test Redis
database configured in `config/settings_test.py`.

To access Django admin, create a local administrator with
`python manage.py createsuperuser`. The SQLite database and virtual
environment are local files and should not be committed.

## Endpoints

- Home page: `/`
- Order summary: `GET /api/orders/summary/`
- Django admin: `/admin/`
- Django Silk profiler: `/silk/`

## ORM benchmark

See [evidence/orm-benchmark.md](evidence/orm-benchmark.md) for the query-count
measurements and their limitations.

In the local SQLite experiment, the query count decreased from 401 to 1 for
200 orders. This result demonstrates a reduction in database queries; it does
not reproduce or confirm the production latency regression described in the
assessment scenario.

## Evidence

- `evidence/orm-benchmark.md` — benchmark details.
- `evidence/silk-optimized.png` — optimized endpoint profiling screenshot.

## Security

The checked-in settings use a local-only development key. Do not use this key,
the console email backend, or Django's development server in production. Keep
local credentials and production secrets out of the repository.
