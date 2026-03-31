from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.core.config import get_settings
from app.domain.schemas import PreprocessMetrics


@dataclass
class PreprocessOutput:
    processed_path: Path
    preview_path: Path
    metrics: PreprocessMetrics
    warnings: list[str]


class PreprocessError(RuntimeError):
    pass


def _estimate_skew(binary: np.ndarray) -> float:
    coords = np.column_stack(np.where(binary < 128))
    if coords.size == 0:
        return 0.0
    rect = cv2.minAreaRect(coords.astype(np.float32))
    angle = rect[-1]
    if angle < -45:
        angle = 90 + angle
    return float(angle)


def _rotate(image: np.ndarray, angle_deg: float) -> np.ndarray:
    height, width = image.shape[:2]
    center = (width // 2, height // 2)
    matrix = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    return cv2.warpAffine(image, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def preprocess_image(input_path: Path, output_dir: Path) -> PreprocessOutput:
    settings = get_settings()
    output_dir.mkdir(parents=True, exist_ok=True)

    image = cv2.imread(str(input_path))
    if image is None:
        raise PreprocessError("Unable to decode uploaded image.")

    height, width = image.shape[:2]
    max_dim = max(height, width)
    scale = min(1.0, settings.max_image_dimension / max_dim)
    if scale < 1.0:
        image = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    threshold = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        15,
    )

    skew_angle = _estimate_skew(threshold)
    rotated = _rotate(image, skew_angle) if abs(skew_angle) > 0.25 else image
    rotated_gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)

    denoised = cv2.fastNlMeansDenoising(rotated_gray, None, 10, 7, 21)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced_gray = clahe.apply(denoised)

    # Keep thresholded output only as a debug/preview artifact. OMR receives the
    # enhanced grayscale image so note fill, stems and flags survive preprocessing.
    preview_binary = cv2.adaptiveThreshold(
        cv2.GaussianBlur(enhanced_gray, (5, 5), 0),
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        15,
    )

    processed = enhanced_gray
    preview = cv2.cvtColor(preview_binary, cv2.COLOR_GRAY2BGR)
    brightness = float(np.mean(rotated_gray))
    contrast = float(np.std(rotated_gray))
    perspective_score = float(min(1.0, contrast / 64.0))

    warnings: list[str] = []
    if brightness < 75:
        warnings.append("Image appears underexposed.")
    if brightness > 220:
        warnings.append("Image appears overexposed.")
    if contrast < 25:
        warnings.append("Image has low contrast.")
    if abs(skew_angle) > 5:
        warnings.append("Image required significant deskewing.")

    processed_path = output_dir / "preprocessed.png"
    preview_path = output_dir / "preview.png"
    cv2.imwrite(str(processed_path), processed)
    cv2.imwrite(str(preview_path), preview)

    metrics = PreprocessMetrics(
        width=int(processed.shape[1]),
        height=int(processed.shape[0]),
        brightness=brightness,
        contrast=contrast,
        skew_angle_deg=skew_angle,
        perspective_score=perspective_score,
    )
    return PreprocessOutput(processed_path=processed_path, preview_path=preview_path, metrics=metrics, warnings=warnings)
