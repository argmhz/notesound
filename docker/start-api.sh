#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import time

from sqlalchemy import create_engine, text

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)

last_error = None
for attempt in range(1, 31):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print(f"Database ready after {attempt} attempt(s).")
        break
    except Exception as exc:  # noqa: BLE001
        last_error = exc
        print(f"Waiting for database ({attempt}/30): {exc}")
        time.sleep(2)
else:
    raise SystemExit(f"Database did not become ready: {last_error}")
PY

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 80
