from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

from app.domain.schemas import MelodyModel


SAMPLE_RATE = 44100
DEFAULT_TEMPO_BPM = 120
TIMING_MODE_RAW = "raw"
TIMING_MODE_QUANTIZED = "quantized"
QUANTIZE_STEP_BEATS = 0.25


def _midi_to_frequency(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def _quantize_beats(value: float, step_beats: float) -> float:
    return round(value / step_beats) * step_beats


def _adsr_envelope(sample_count: int) -> np.ndarray:
    if sample_count <= 1:
        return np.ones(max(sample_count, 1), dtype=np.float32)

    attack = max(1, int(sample_count * 0.02))
    decay = max(1, int(sample_count * 0.10))
    release = max(1, int(sample_count * 0.12))
    sustain = max(1, sample_count - attack - decay - release)

    attack_curve = np.linspace(0.0, 1.0, attack, endpoint=False, dtype=np.float32)
    decay_curve = np.linspace(1.0, 0.75, decay, endpoint=False, dtype=np.float32)
    sustain_curve = np.full(sustain, 0.75, dtype=np.float32)
    release_curve = np.linspace(0.75, 0.0, release, endpoint=True, dtype=np.float32)
    envelope = np.concatenate([attack_curve, decay_curve, sustain_curve, release_curve])
    if envelope.size < sample_count:
        envelope = np.pad(envelope, (0, sample_count - envelope.size), mode="edge")
    return envelope[:sample_count]


def render_melody_to_wav(
    melody: MelodyModel,
    output_path: Path,
    tempo_bpm: int = DEFAULT_TEMPO_BPM,
    timing_mode: str = TIMING_MODE_RAW,
) -> Path:
    if not melody.notes:
        raise ValueError("Melody contains no notes.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    seconds_per_beat = 60.0 / tempo_bpm
    playable_notes = [melody_note for melody_note in melody.notes if melody_note.pitch.midi is not None]
    if not playable_notes:
        raise ValueError("Melody contains no playable notes.")

    if timing_mode not in {TIMING_MODE_RAW, TIMING_MODE_QUANTIZED}:
        raise ValueError(f"Unsupported timing_mode: {timing_mode}")

    quantize = timing_mode == TIMING_MODE_QUANTIZED

    last_end_beat = max(
        (
            _quantize_beats((melody_note.start_beat if melody_note.start_beat is not None else float(index)), QUANTIZE_STEP_BEATS)
            if quantize
            else (melody_note.start_beat if melody_note.start_beat is not None else float(index))
        )
        + (
            max(QUANTIZE_STEP_BEATS, _quantize_beats(melody_note.duration_beats, QUANTIZE_STEP_BEATS))
            if quantize
            else melody_note.duration_beats
        )
        for index, melody_note in enumerate(playable_notes)
    )
    total_samples = max(1, int(last_end_beat * seconds_per_beat * SAMPLE_RATE))
    audio = np.zeros(total_samples, dtype=np.float32)

    for index, melody_note in enumerate(playable_notes):
        midi = melody_note.pitch.midi
        if midi is None:
            continue

        start_beat = melody_note.start_beat if melody_note.start_beat is not None else float(index)
        duration_beats = melody_note.duration_beats
        if quantize:
            start_beat = _quantize_beats(start_beat, QUANTIZE_STEP_BEATS)
            duration_beats = max(QUANTIZE_STEP_BEATS, _quantize_beats(duration_beats, QUANTIZE_STEP_BEATS))
        duration_seconds = max(0.08, duration_beats * seconds_per_beat)
        start_sample = int(start_beat * seconds_per_beat * SAMPLE_RATE)
        sample_count = max(1, int(SAMPLE_RATE * duration_seconds))
        end_sample = min(total_samples, start_sample + sample_count)
        actual_sample_count = max(1, end_sample - start_sample)

        t = np.linspace(0, actual_sample_count / SAMPLE_RATE, actual_sample_count, endpoint=False)
        frequency = _midi_to_frequency(midi)

        # Layered voice that stays readable for single notes and small chords.
        wave_data = (
            0.62 * np.sin(2 * math.pi * frequency * t)
            + 0.23 * np.sin(2 * math.pi * frequency * 2 * t)
            + 0.10 * np.sin(2 * math.pi * frequency * 3 * t)
            + 0.05 * np.sin(2 * math.pi * frequency * 0.5 * t)
        )
        wave_data *= _adsr_envelope(actual_sample_count)
        wave_data *= 0.38

        audio[start_sample:end_sample] += wave_data.astype(np.float32)

    peak = float(np.max(np.abs(audio)))
    if peak > 0.0:
        audio = audio * (0.92 / peak)
    audio = np.tanh(audio * 1.1)
    pcm = (audio * 32767).astype(np.int16)

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm.tobytes())

    return output_path
