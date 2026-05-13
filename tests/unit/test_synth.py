import wave
from pathlib import Path

from app.domain.schemas import MelodyModel, MelodyNote, PitchModel
from app.services.music.synth import TIMING_MODE_QUANTIZED, TIMING_MODE_RAW, render_melody_to_wav


def test_render_melody_to_wav_creates_wave_file(tmp_path: Path):
    melody = MelodyModel(
        notes=[
            MelodyNote(start_beat=0.0, duration_beats=1.0, pitch=PitchModel(step="C", octave=4, midi=60)),
            MelodyNote(start_beat=2.0, duration_beats=2.0, pitch=PitchModel(step="D", octave=4, midi=62)),
        ]
    )

    output = render_melody_to_wav(melody, tmp_path / "melody.wav", tempo_bpm=120)

    assert output.exists()
    data = output.read_bytes()
    assert data[:4] == b"RIFF"
    assert len(data) > 170000


def test_render_melody_to_wav_quantized_timing_changes_event_grid(tmp_path: Path):
    melody = MelodyModel(
        notes=[
            MelodyNote(start_beat=0.13, duration_beats=0.37, pitch=PitchModel(step="C", octave=4, midi=60)),
            MelodyNote(start_beat=0.71, duration_beats=0.62, pitch=PitchModel(step="E", octave=4, midi=64)),
            MelodyNote(start_beat=1.42, duration_beats=1.18, pitch=PitchModel(step="G", octave=4, midi=67)),
        ]
    )

    raw_path = render_melody_to_wav(melody, tmp_path / "melody-raw.wav", tempo_bpm=120, timing_mode=TIMING_MODE_RAW)
    quantized_path = render_melody_to_wav(
        melody,
        tmp_path / "melody-quantized.wav",
        tempo_bpm=120,
        timing_mode=TIMING_MODE_QUANTIZED,
    )

    with wave.open(str(raw_path), "rb") as raw_wave:
        raw_frames = raw_wave.getnframes()
    with wave.open(str(quantized_path), "rb") as quantized_wave:
        quantized_frames = quantized_wave.getnframes()

    assert raw_path.exists()
    assert quantized_path.exists()
    assert raw_path.read_bytes()[:4] == b"RIFF"
    assert quantized_path.read_bytes()[:4] == b"RIFF"
    assert raw_frames != quantized_frames
