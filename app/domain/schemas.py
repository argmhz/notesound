from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"


class ArtifactKind(StrEnum):
    original = "original"
    preprocessed = "preprocessed"
    preview = "preview"
    musicxml = "musicxml"
    audio = "audio"
    debug = "debug"


class ArtifactRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    kind: ArtifactKind
    path: str
    content_type: str
    size_bytes: int
    url: str | None = None


class PreprocessMetrics(BaseModel):
    width: int
    height: int
    brightness: float
    contrast: float
    skew_angle_deg: float = 0.0
    perspective_score: float = 0.0


class RecognitionInput(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    preprocess_metrics: PreprocessMetrics | None = None


class PitchModel(BaseModel):
    step: str
    alter: int = 0
    octave: int
    midi: int | None = None


class MelodyNote(BaseModel):
    start_beat: float | None = None
    measure: int | None = None
    beat: float | None = None
    duration_beats: float
    pitch: PitchModel
    tie: str | None = None
    accidental: str | None = None
    source_staff: int | None = None
    confidence: float = 0.5


class MelodyModel(BaseModel):
    notes: list[MelodyNote] = Field(default_factory=list)


class ScoreSummary(BaseModel):
    format: str = "musicxml"
    musicxml_artifact_url: str | None = None
    measures: int | None = None
    parts: int | None = None
    time_signature: str | None = None
    key_signature: str | None = None


class TablaturePlaceholder(BaseModel):
    supported: bool = False
    reason: str = "Tablature is not implemented in the MVP."


class RecognitionResultPayload(BaseModel):
    job_id: str
    status: JobStatus
    input: RecognitionInput
    warnings: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    score: ScoreSummary | None = None
    melody: MelodyModel | None = None
    tablature: TablaturePlaceholder = Field(default_factory=TablaturePlaceholder)


class RecognitionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    timings_ms: dict[str, int] = Field(default_factory=dict)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    result_available: bool = False


class RecognitionCreateResponse(BaseModel):
    job_id: str
    status: JobStatus


class RecognitionOptions(BaseModel):
    expected_clef: str | None = None
    crop_mode: str | None = None
    return_artifacts: bool = True


class RecognitionJobState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: JobStatus
    filename: str
    content_type: str
    size_bytes: int
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    timings_ms: dict[str, int] = Field(default_factory=dict)
    preprocess_metrics: dict[str, Any] = Field(default_factory=dict)
    result_payload: dict[str, Any] | None = None
