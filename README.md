# Notesound

FastAPI-baseret MVP til upload af nodebilleder, preprocess, OMR-transskription til MusicXML og JSON-output med genkendt melodi.

## Spec

Projektets MVP-spec findes i [specs/mvp-spec.md](./specs/mvp-spec.md).

## Bruno

En Bruno collection ligger i [bruno/Notesound](./bruno/Notesound).  
Brug environment-filen `Local.bru`, sæt `imagePath`, kør `Create Recognition`, og gem derefter `job_id` i `jobId`-variablen til status/result/audio/artifact requests.

## Docker

```bash
docker compose build
docker compose up api db
```

Kør test i container:

```bash
docker compose run --rm test
```

API-containeren venter på, at PostgreSQL er klar, før den kører migrations og starter serveren.
API'en lytter internt i containeren på port `80` og eksponeres via Compose som `localhost:8000`.

## Lokal kørsel

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Standarddatabase er SQLite for lokal udvikling. Docker Compose bruger PostgreSQL til API-service og SQLite i den isolerede test-container.

## API

- `POST /v1/recognitions`
- `GET /v1/recognitions/{job_id}`
- `GET /v1/recognitions/{job_id}/result`
- `GET /v1/recognitions/{job_id}/audio`
- `GET /v1/recognitions/{job_id}/artifacts/{name}`
- `GET /healthz`

## Bemærkninger

- `homr` forventes installeret i runtime-miljøet.
- MVP’et kører jobs lokalt i baggrundstråde. Queue kan senere erstattes uden API-brud.
- App-containeren kører `alembic upgrade head` ved start, så databasen er migreret før API’en eksponeres.
