from fastapi import FastAPI

from app.api.routes import api_router, router
from app.core.config import get_settings
from app.core import db as db_module
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    db_module.Base.metadata.create_all(bind=db_module.engine)

    app = FastAPI(title=settings.app_name)
    app.include_router(router)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
