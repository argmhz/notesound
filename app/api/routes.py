from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import get_job_repository
from app.core.config import get_settings
from app.domain.schemas import ArtifactKind, JobStatus, RecognitionCreateResponse, RecognitionOptions, RecognitionResultPayload
from app.repositories.jobs import JobRepository
from app.services.music.synth import DEFAULT_TEMPO_BPM, render_melody_to_wav
from app.workers.runner import get_job_runner


router = APIRouter()
api_router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@api_router.post("/recognitions", response_model=RecognitionCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_recognition(
    request: Request,
    image: UploadFile = File(...),
    expected_clef: str | None = Form(default=None),
    crop_mode: str | None = Form(default=None),
    return_artifacts: bool = Form(default=True),
    repository: JobRepository = Depends(get_job_repository),
) -> RecognitionCreateResponse:
    settings = get_settings()
    if image.content_type not in settings.allowed_image_types:
        raise HTTPException(status_code=415, detail="Unsupported image content type.")

    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(payload) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=413, detail="Uploaded file exceeds size limit.")

    options = RecognitionOptions(
        expected_clef=expected_clef,
        crop_mode=crop_mode,
        return_artifacts=return_artifacts,
    )
    job = repository.create_job(
        filename=image.filename or "upload.bin",
        content_type=image.content_type,
        size_bytes=len(payload),
        options=options.model_dump(mode="json"),
    )

    original_path = settings.artifacts_dir / job.id / "original" / (image.filename or "source")
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes(payload)
    repository.save_artifact(job=job, name="original", kind=ArtifactKind.original, path=original_path, content_type=image.content_type)

    runner = get_job_runner()
    runner.submit(job.id)
    return RecognitionCreateResponse(job_id=job.id, status=JobStatus.queued)


@api_router.get("/recognitions/{job_id}")
def get_recognition(job_id: str, request: Request, repository: JobRepository = Depends(get_job_repository)):
    job = repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Recognition job not found.")
    return repository.to_job_response(job, lambda name: str(request.url_for("get_artifact", job_id=job_id, name=name)))


@api_router.get("/recognitions/{job_id}/result", response_model=RecognitionResultPayload)
def get_recognition_result(job_id: str, repository: JobRepository = Depends(get_job_repository)):
    job = repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Recognition job not found.")
    if job.result_payload is None:
        raise HTTPException(status_code=409, detail=f"Recognition job is currently {job.status}.")
    return RecognitionResultPayload.model_validate(job.result_payload)


@api_router.get("/recognitions/{job_id}/audio", name="get_recognition_audio")
def get_recognition_audio(
    job_id: str,
    repository: JobRepository = Depends(get_job_repository),
    tempo_bpm: int = Query(default=DEFAULT_TEMPO_BPM, ge=40, le=240),
    download: bool = Query(default=False),
):
    job = repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Recognition job not found.")
    if job.result_payload is None:
        raise HTTPException(status_code=409, detail=f"Recognition job is currently {job.status}.")

    payload = RecognitionResultPayload.model_validate(job.result_payload)
    if payload.melody is None or not payload.melody.notes:
        raise HTTPException(status_code=422, detail="Recognition result does not contain a playable melody.")

    artifact_name = f"audio-wav-{tempo_bpm}"
    existing = repository.get_artifact_by_name(job, artifact_name)
    if existing is not None and Path(existing.path).exists():
        audio_path = Path(existing.path)
    else:
        settings = get_settings()
        audio_path = settings.artifacts_dir / job.id / "audio" / f"melody-{tempo_bpm}bpm.wav"
        try:
            render_melody_to_wav(payload.melody, audio_path, tempo_bpm=tempo_bpm)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        repository.save_artifact(
            job=job,
            name=artifact_name,
            kind=ArtifactKind.audio,
            path=audio_path,
            content_type="audio/wav",
        )

    return FileResponse(
        path=audio_path,
        media_type="audio/wav",
        filename=audio_path.name if download else None,
    )


@api_router.get("/recognitions/{job_id}/artifacts/{name}", name="get_artifact")
def get_artifact(job_id: str, name: str, repository: JobRepository = Depends(get_job_repository)):
    job = repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Recognition job not found.")

    artifact = repository.get_artifact_by_name(job, name)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    path = Path(artifact.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact missing on disk.")
    return FileResponse(path=path, media_type=artifact.content_type, filename=path.name)
