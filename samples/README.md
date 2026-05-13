# Notesound Sample Dataset

This folder is the starting point for the MVP evaluation dataset.

## Fast Local Flow

If you just want to try one or more images locally:

1. Put the image files in `samples/inbox/`
2. Run:

```bash
docker compose -f docker-compose.local.yml run --rm test python scripts/process_inbox.py
```

Optional tempo override:

```bash
docker compose -f docker-compose.local.yml run --rm test python scripts/process_inbox.py --tempo-bpm 100
```

The script creates or updates `samples/cases/<image-name>/` with:

```text
samples/cases/<case-id>/
  original.jpg|png|webp
  preprocess/
    preprocessed.png
    preview.png
  omr/
    result.musicxml
    original/
    enhanced/
    binary/
    ...possible homr debug files...
  audio/
    melody-120bpm-raw.wav
    melody-120bpm-quantized.wav
  observed.json
  expected.draft.json
  notes.md
```

`observed.json` is the raw observed result from the current pipeline.
`expected.draft.json` is only a draft generated from that result. Review it manually before renaming it to `expected.json`.
`audio/melody-*-raw.wav` is the direct timing from OMR.
`audio/melody-*-quantized.wav` snaps timing to a 16th-note grid for faster quality checks.

Quick playback examples:

```bash
ffplay -autoexit -nodisp samples/cases/<case-id>/audio/melody-120bpm-raw.wav
```

```bash
aplay samples/cases/<case-id>/audio/melody-120bpm-quantized.wav
```

## Goal

Build a small, curated set of real sheet-music images so OMR changes can be evaluated against expected output instead of judged by ear or guesswork.

## Case Structure

Each case should live in `samples/cases/<case-id>/`:

```text
samples/cases/sample-001/
  original.jpg
  expected.json
  notes.md
```

`samples/inbox/` is intended for local drop-in testing and is ignored by git except for `.gitkeep`.
Generated/debug files may be added locally, but should not be committed unless they are intentional fixtures.

## Expected JSON Format

```json
{
  "title": "Short description",
  "image": "original.jpg",
  "expected": {
    "time_signature": "4/4",
    "notes": [
      {
        "midi": 60,
        "duration_beats": 1.0
      }
    ]
  }
}
```

Minimum useful fields:

- `expected.time_signature`
- `expected.notes[].midi`
- `expected.notes[].duration_beats`

## Current Priority

Start with 5-10 real mobile photos. For the first 1-2 cases, manually enter expected pitch and rhythm so `scripts/eval_samples.py` can score OMR output.
