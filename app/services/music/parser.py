from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from defusedxml.ElementTree import fromstring as secure_fromstring
from music21 import converter, note, pitch, stream

from app.domain.schemas import (
    ArtifactRef,
    MelodyModel,
    MelodyNote,
    PitchModel,
    RecognitionInput,
    RecognitionResultPayload,
    ScoreSummary,
    TablaturePlaceholder,
)


class MusicParseError(RuntimeError):
    pass


DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)


@dataclass
class _TimelineNote:
    start_beat: float
    measure: int | None
    beat: float | None
    duration_beats: float
    pitch_model: PitchModel
    tie: str | None
    accidental: str | None
    source_staff: int
    confidence: float


def _extract_key_signature(score: stream.Score) -> str | None:
    key_signature = score.recurse().getElementsByClass("KeySignature").first()
    if key_signature is None:
        return None
    sharps = getattr(key_signature, "sharps", None)
    return str(sharps) if sharps is not None else None


def _extract_time_signature(score: stream.Score) -> str | None:
    ts = score.recurse().getElementsByClass("TimeSignature").first()
    return ts.ratioString if ts is not None else None


def _build_pitch_model(p: pitch.Pitch) -> PitchModel:
    return PitchModel(step=p.step, alter=int(p.accidental.alter) if p.accidental else 0, octave=int(p.octave), midi=p.midi)


def _same_pitch(left: PitchModel, right: PitchModel) -> bool:
    return (left.step, left.alter, left.octave, left.midi) == (right.step, right.alter, right.octave, right.midi)


def _merge_tied_notes(notes: list[_TimelineNote]) -> list[_TimelineNote]:
    merged: list[_TimelineNote] = []
    active: _TimelineNote | None = None

    for timeline_note in notes:
        if timeline_note.tie == "start":
            candidate = _TimelineNote(**timeline_note.__dict__)
            merged.append(candidate)
            active = candidate
            continue

        if timeline_note.tie in {"continue", "stop"} and active and _same_pitch(active.pitch_model, timeline_note.pitch_model):
            active.duration_beats += timeline_note.duration_beats
            if timeline_note.tie == "stop":
                active.tie = None
                active = None
            else:
                active.tie = "continue"
            continue

        candidate = _TimelineNote(**timeline_note.__dict__)
        candidate.tie = None if candidate.tie == "stop" else candidate.tie
        merged.append(candidate)
        active = candidate if candidate.tie in {"start", "continue"} else None

    return merged


def melody_from_score(score: stream.Score) -> MelodyModel:
    notes: list[_TimelineNote] = []
    part_index = 0
    for part in score.parts:
        for element in part.recurse().notesAndRests:
            if not isinstance(element, note.Note):
                continue
            measure = element.getContextByClass(stream.Measure)
            notes.append(
                _TimelineNote(
                    start_beat=float(element.getOffsetInHierarchy(part)),
                    measure=measure.number if measure is not None else None,
                    beat=float(element.beat) if element.beat is not None else None,
                    duration_beats=float(element.duration.quarterLength),
                    pitch_model=_build_pitch_model(element.pitch),
                    tie=element.tie.type if element.tie else None,
                    accidental=element.pitch.accidental.name if element.pitch.accidental else None,
                    source_staff=part_index,
                    confidence=0.75,
                )
            )
        if notes:
            break
        part_index += 1

    merged_notes = _merge_tied_notes(sorted(notes, key=lambda item: item.start_beat))
    return MelodyModel(
        notes=[
            MelodyNote(
                start_beat=item.start_beat,
                measure=item.measure,
                beat=item.beat,
                duration_beats=item.duration_beats,
                pitch=item.pitch_model,
                tie=item.tie,
                accidental=item.accidental,
                source_staff=item.source_staff,
                confidence=item.confidence,
            )
            for item in merged_notes
        ]
    )


def parse_musicxml(musicxml_path: Path):
    try:
        xml_text = musicxml_path.read_text(encoding="utf-8")
        secure_fromstring(DOCTYPE_RE.sub("", xml_text))
        score = converter.parse(str(musicxml_path))
    except (ET.ParseError, Exception) as exc:  # noqa: BLE001
        raise MusicParseError(f"Unable to parse MusicXML: {exc}") from exc
    return score


def build_result_payload(
    *,
    job_id: str,
    status: str,
    recognition_input: RecognitionInput,
    warnings: list[str],
    confidence: float,
    artifacts: list[ArtifactRef],
    musicxml_url: str | None,
    musicxml_path: Path,
) -> RecognitionResultPayload:
    score = parse_musicxml(musicxml_path)
    melody = melody_from_score(score)

    parts = len(score.parts)
    measures = max((len(part.getElementsByClass(stream.Measure)) for part in score.parts), default=0)
    summary = ScoreSummary(
        format="musicxml",
        musicxml_artifact_url=musicxml_url,
        measures=measures,
        parts=parts,
        time_signature=_extract_time_signature(score),
        key_signature=_extract_key_signature(score),
    )

    return RecognitionResultPayload(
        job_id=job_id,
        status=status,
        input=recognition_input,
        warnings=warnings,
        confidence=confidence,
        artifacts=artifacts,
        score=summary,
        melody=melody,
        tablature=TablaturePlaceholder(),
    )
