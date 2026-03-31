from io import BytesIO

from PIL import Image


def _make_test_png() -> bytes:
    image = Image.new("RGB", (128, 128), color=(255, 255, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_health(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_recognition_and_fetch_result(client):
    response = client.post(
        "/v1/recognitions",
        files={"image": ("score.png", _make_test_png(), "image/png")},
        data={"return_artifacts": "true"},
    )
    assert response.status_code == 202
    payload = response.json()
    job_id = payload["job_id"]

    status_response = client.get(f"/v1/recognitions/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "succeeded"

    result_response = client.get(f"/v1/recognitions/{job_id}/result")
    assert result_response.status_code == 200
    result = result_response.json()

    assert result["job_id"] == job_id
    assert result["status"] == "succeeded"
    assert result["score"]["format"] == "musicxml"
    assert len(result["melody"]["notes"]) == 2
    assert result["melody"]["notes"][0]["duration_beats"] == 1.0
    assert result["melody"]["notes"][0]["start_beat"] == 0.0
    assert result["melody"]["notes"][1]["duration_beats"] == 2.0
    assert result["melody"]["notes"][1]["start_beat"] == 2.0
    assert result["tablature"]["supported"] is False

    audio_response = client.get(f"/v1/recognitions/{job_id}/audio")
    assert audio_response.status_code == 200
    assert audio_response.headers["content-type"] == "audio/wav"
    assert audio_response.content[:4] == b"RIFF"
    assert len(audio_response.content) > 170000
