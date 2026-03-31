# Notesound MVP Spec

## Formål

Notesound er et backend-API, der modtager et billede af et nodeark, preprocesser billedet, forsøger at transskribere noderne og returnerer den genkendte melodi i et stabilt JSON-format.  
MVP'et er designet til senere at kunne understøtte både mobilapp-klienter og tablatur uden at bryde de centrale kontrakter.

## MVP-scope

### In scope

- Upload af nodebillede via HTTP API
- Asynkront recognition-job med `job_id`
- Preprocessing af mobilfotos og scanninger
- OMR gennem udskiftelig engine-adapter
- MusicXML som internt kanonisk format
- JSON-resultat med melodi, metadata, warnings og confidence
- Artifact-lagring for originalt billede, preprocess-output og MusicXML
- Docker-baseret drift

### Out of scope

- Egen OMR-modeltræning
- Realtidsstreaming eller websocket-opdateringer
- Fuld polyfonisk fortolkning
- Avancerede musiksymboler som dynamik, artikulation og ornamentik
- Færdig tablaturgenerering
- Auth, rate limiting og multi-tenant drift

## Målgruppe og brug

- Primær bruger i MVP er en kommende mobilapp eller anden klient, der uploader et nodefoto og poller på status.
- API'et skal være robust nok til langsom behandlingstid og uforudsigelige mobilfotos.

## Overordnet arkitektur

### Flow

1. Klient uploader billede til `POST /v1/recognitions`
2. API opretter job i databasen og gemmer originalt artifact
3. Lokal worker preprocesser billedet
4. OMR-engine forsøger at generere MusicXML
5. MusicXML parses og normaliseres til internt score-view
6. Resultatet projekteres til klientvenligt JSON-format
7. Klient henter status og resultat via `job_id`

### Komponenter

- `FastAPI`: HTTP-lag og kontrakter
- `SQLAlchemy` + `Alembic`: persistence og migrations
- `OpenCV`: preprocessing
- `homr`: primær OMR-engine i MVP
- `music21`: MusicXML-parsing og melodiekstraktion
- Lokal filstorage: artifacts
- Docker Compose: lokal drift og test

## Teknologistak

- Sprog: Python 3.11
- API: FastAPI, Pydantic
- DB: PostgreSQL i Compose, SQLite i isoleret test/development flow
- OMR: `homr`
- Billedbehandling: `opencv-python-headless`, `numpy`, `Pillow`
- Musikanalyse: `music21`
- XML-sikkerhed: `defusedxml`
- Drift: Docker, Docker Compose
- Test: pytest, pytest-asyncio, httpx

## Begrundelse for centrale valg

- Asynkront job-API er valgt, fordi OMR kan være langsomt og skal passe til mobilklienter.
- `homr` er valgt som MVP-engine, fordi den er målrettet kamerafotos og producerer MusicXML.
- `MusicXML` er centralt mellemformat, fordi det er bredt understøttet og gør senere tablatur-/eksportlag lettere.
- OMR holdes bag et interface, så anden engine senere kan tilføjes uden at ændre API-kontrakten.

## Funktionelle krav

### Upload

- Systemet skal acceptere `jpeg`, `png` og `webp`
- Upload skal afvises, hvis filen er tom eller overskrider størrelsesgrænsen

### Jobstyring

- Et upload skal oprette et job med status `queued`
- Jobstatus skal kunne være `queued`, `processing`, `succeeded`, `failed`
- Resultat må først være tilgængeligt, når jobbet er fuldført

### Preprocessing

- Systemet skal forsøge resize, grayscale, blur, adaptive threshold og deskew
- Systemet skal måle mindst brightness, contrast, skew og en simpel perspective-score
- Preprocess warnings skal eksponeres til klienten

### OMR

- OMR-laget skal være udskifteligt via et internt `OmrEngine` interface
- Fejl fra OMR skal normaliseres til stabile fejlkoder

### Resultat

- Resultatet skal returnere struktureret JSON med score-summary og melody-notes
- Tablatur skal være reserveret i kontrakten som ikke-understøttet placeholder

## Ikke-funktionelle krav

- Hele systemet skal kunne bygges og testes i Docker
- API-kontrakten skal være stabil nok til en mobilapp-klient
- Artifact-sporbarhed skal gøre debugging muligt
- Koden skal være struktureret, så queue, storage og OMR-engine senere kan udskiftes

## API-spec

### `GET /healthz`

Returnerer:

```json
{
  "status": "ok"
}
```

### `POST /v1/recognitions`

#### Input

Multipart form-data:

- `image`: billedfil, påkrævet
- `expected_clef`: optional string
- `crop_mode`: optional string
- `return_artifacts`: optional bool

#### Output

```json
{
  "job_id": "uuid",
  "status": "queued"
}
```

### `GET /v1/recognitions/{job_id}`

Returnerer jobstatus, warnings, timings og artifact-links.

Eksempel:

```json
{
  "job_id": "uuid",
  "status": "processing",
  "created_at": "2026-03-31T12:00:00Z",
  "updated_at": "2026-03-31T12:00:03Z",
  "warnings": [],
  "error_code": null,
  "error_message": null,
  "timings_ms": {
    "preprocess": 120,
    "omr": 1800,
    "total": 2050
  },
  "artifacts": [],
  "result_available": false
}
```

### `GET /v1/recognitions/{job_id}/result`

Returnerer fuldt resultat, når jobstatus er `succeeded`.

Eksempel:

```json
{
  "job_id": "uuid",
  "status": "succeeded",
  "input": {
    "filename": "score.png",
    "content_type": "image/png",
    "size_bytes": 123456,
    "width": 1080,
    "height": 1440,
    "preprocess_metrics": {
      "width": 1080,
      "height": 1440,
      "brightness": 181.2,
      "contrast": 42.1,
      "skew_angle_deg": -1.8,
      "perspective_score": 0.66
    }
  },
  "warnings": [],
  "confidence": 0.82,
  "artifacts": [
    {
      "name": "original",
      "kind": "original",
      "path": "/app/data/artifacts/...",
      "content_type": "image/png",
      "size_bytes": 123456,
      "url": "/v1/recognitions/uuid/artifacts/original"
    }
  ],
  "score": {
    "format": "musicxml",
    "musicxml_artifact_url": "/v1/recognitions/uuid/artifacts/musicxml",
    "measures": 8,
    "parts": 1,
    "time_signature": "4/4",
    "key_signature": "0"
  },
  "melody": {
    "notes": [
      {
        "measure": 1,
        "beat": 1.0,
        "duration_beats": 1.0,
        "pitch": {
          "step": "C",
          "alter": 0,
          "octave": 4,
          "midi": 60
        },
        "tie": null,
        "accidental": null,
        "source_staff": 0,
        "confidence": 0.75
      }
    ]
  },
  "tablature": {
    "supported": false,
    "reason": "Tablature is not implemented in the MVP."
  }
}
```

### `GET /v1/recognitions/{job_id}/artifacts/{name}`

Returnerer et artifact som fil-download eller inline-filresponse.

### `GET /v1/recognitions/{job_id}/audio`

Genererer og returnerer en simpel monofonisk WAV af den genkendte melodi.

Query params:

- `tempo_bpm`: optional integer, default `120`
- `download`: optional bool, default `false`

Response:

- `audio/wav`

Bemærkning:

- Dette er en pragmatisk MVP-afspilning af melodien, ikke en realistisk instrumentgengivelse.

## Domænemodel

### RecognitionJob

- `id`
- `status`
- `filename`
- `content_type`
- `size_bytes`
- `options`
- `warnings`
- `preprocess_metrics`
- `timings_ms`
- `error_code`
- `error_message`
- `result_payload`
- `created_at`
- `updated_at`

### Artifact

- `name`
- `kind`
- `path`
- `content_type`
- `size_bytes`

### Resultatmodel

- `input`
- `warnings`
- `confidence`
- `artifacts`
- `score`
- `melody`
- `tablature`

## Artifact-strategi

MVP gemmer artifacts lokalt på filsystemet under en job-specifik mappe:

- `original`
- `preprocessed`
- `preview`
- `musicxml`

Artifacts bruges både til klientoutput og debugging.

## Preprocessing-spec

Aktuel MVP-pipeline:

- image decode
- resize ned til maks dimension
- grayscale conversion
- gaussian blur
- adaptive threshold
- deskew via estimeret vinkel
- preprocess preview artifact

Aktuelle metrics:

- `brightness`
- `contrast`
- `skew_angle_deg`
- `perspective_score`

## OMR-spec

- Primær engine: `homr`
- Integrationstype: CLI-baseret adapter
- Input: preprocesset billede på disk
- Output: MusicXML-fil på disk

### Fejlkoder

- `missing_input`
- `preprocess_failed`
- `omr_unavailable`
- `omr_failed`
- `musicxml_parse_failed`
- `internal_error`

## Confidence og warnings

Confidence i MVP er heuristisk og baseret på:

- preprocess-kvalitet
- deskew-behov
- kontrastniveau
- antal warnings

Warnings er ikke-fatal information, som klienten kan vise til brugeren.

## Kode- og mappestruktur

```text
app/
  api/
  core/
  domain/
  repositories/
  services/
    preprocess/
    omr/
    music/
  workers/
alembic/
docker/
tests/
specs/
```

## Teststrategi

### Unit-tests

- preprocess genererer artifacts og metrics

### Integrationstests

- health endpoint
- create recognition
- status lookup
- result lookup

### Testprincip

- Tests køres i Docker
- OMR er mocked i tests via fake engine
- Container-testene verificerer API- og pipeline-integration uden at kræve live `homr`

## Kendte begrænsninger

- Rigtig `homr`-transskription er ikke endnu dækket af automatiske tests
- Mobilfoto-perspektiv er kun simpelt håndteret i MVP
- Melodi udledes som første parsebare note-sekvens, ikke fuld musikalsk topstemme-analyse
- Tablatur er endnu ikke implementeret

## Udvidelsesplan efter MVP

### Mobilapp

- auth/token-beskyttelse
- polling eller websocket events
- object storage i stedet for lokal disk
- rigtig job-queue i stedet for lokal thread-runner

### Tablatur

- tilføj `instrument_profile`, tuning og streng/fret-præferencer
- implementér separat `ScoreModel -> TabProjection`
- eksponér tablatur som ekstra resultatfelt uden at bryde nuværende JSON-form

### OMR

- alternativ engine-adapter som `oemer`
- bedre mobilfoto-forbedring med crop/perspective correction
- regressionstest med rigtige nodebilleder

## Acceptkriterier for MVP

- Projektet kan bygges i Docker
- Test-containeren passerer
- API kan modtage et billede og oprette et job
- Job kan gennemløbe preprocess, OMR-adapter og MusicXML-normalisering
- Resultatet kan hentes som JSON med score, melody, warnings og artifacts
- Systemet er struktureret, så mobilapp og tablatur kan tilføjes senere uden grundlæggende redesign
