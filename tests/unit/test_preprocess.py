from pathlib import Path

import cv2
import numpy as np

from app.services.preprocess.pipeline import preprocess_image


def test_preprocess_generates_metrics_and_artifacts(tmp_path: Path):
    image = np.full((200, 200, 3), 255, dtype=np.uint8)
    cv2.line(image, (10, 100), (190, 100), (0, 0, 0), 2)
    input_path = tmp_path / "input.png"
    cv2.imwrite(str(input_path), image)

    result = preprocess_image(input_path, tmp_path / "out")

    assert result.processed_path.exists()
    assert result.preview_path.exists()
    assert result.metrics.width == 200
    assert result.metrics.height == 200

