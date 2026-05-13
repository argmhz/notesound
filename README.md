# Notesound

FastAPI-baseret MVP til upload af nodebilleder, preprocess, OMR-transskription til MusicXML og JSON-output med genkendt melodi.

## Spec

Projektets MVP-spec findes i [specs/mvp-spec.md](./specs/mvp-spec.md).

## Sample Eval

MVP'ets næste prioritet er et lille sample/eval-datasæt. Se [samples/README.md](./samples/README.md).

Hvis du bare vil teste et billede uden API'et:

1. Læg billedet i `samples/inbox/`
2. Kør:

```bash
docker compose -f docker-compose.local.yml run --rm test python scripts/process_inbox.py
```

Det genererer en case i `samples/cases/<image-navn>/` med preprocess-output, MusicXML, WAV-audio, `observed.json` og `expected.draft.json`.

Lyt hurtigt til resultatet:

```bash
ffplay -autoexit -nodisp samples/cases/<case-id>/audio/melody-120bpm-raw.wav
ffplay -autoexit -nodisp samples/cases/<case-id>/audio/melody-120bpm-quantized.wav
```

Kør lokal evaluering af cases med:

```bash
docker compose -f docker-compose.local.yml run --rm test python scripts/eval_samples.py
```

Scriptet forventer `expected.json` og eventuelt et `.musicxml` output i hver case-mappe.

## Bruno

En Bruno collection ligger i [bruno/Notesound](./bruno/Notesound).  
Brug environment-filen `Local.bru`, sæt `imagePath`, kør `Create Recognition`, og gem derefter `job_id` i `jobId`-variablen til status/result/audio/artifact requests.

## Docker

Lokal Docker Compose uden proxy-settings:

```bash
docker compose -f docker-compose.local.yml build
docker compose -f docker-compose.local.yml up api db
```

Server/deployment Compose med `nginx-proxy`-settings:

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

### nginx-proxy Deployment

Til `nginxproxy/nginx-proxy` er `api`-servicen sat op med:

- `VIRTUAL_HOST=notesound.codewizard.dk`
- `VIRTUAL_PORT=80`
- `CLIENT_MAX_BODY_SIZE=25m`
- `NOTESOUND_MAX_UPLOAD_SIZE_BYTES=26214400`

Hvis din proxy bruger et delt eksternt Docker-netværk, skal `api`-servicen også tilknyttes det netværk. Der er en kommenteret sektion i [docker-compose.yml](./docker-compose.yml), som kan aktiveres og tilpasses til det rigtige netværksnavn.

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
