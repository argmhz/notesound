from app.core.config import get_settings
from app.services.omr.base import OmrEngine
from app.services.omr.homr_engine import HomrEngine


def get_omr_engine() -> OmrEngine:
    settings = get_settings()
    if settings.omr_engine == "homr":
        return HomrEngine()
    raise ValueError(f"Unsupported OMR engine: {settings.omr_engine}")

