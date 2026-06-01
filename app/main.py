import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import engine
from app.i18n import SUPPORTED_LANGUAGES, detect_language, get_translations
from app.migrate import run_migrations
from app.models import Base
from app.routes import event_admin, guest, public, site_admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await run_migrations(conn)
    logger.info("Database tables created/verified")
    yield


class I18nMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/static"):
            return await call_next(request)

        cookie_lang = request.cookies.get("wbw_lang")
        accept_lang = request.headers.get("accept-language")
        lang = detect_language(accept_lang, cookie_lang)

        request.state.lang = lang
        request.state.t = get_translations(lang)
        request.state.supported_languages = SUPPORTED_LANGUAGES

        return await call_next(request)


app = FastAPI(title="Who Brings What?", lifespan=lifespan)
app.add_middleware(I18nMiddleware)

static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/set-lang/{lang}")
async def set_language(request: Request, lang: str):
    if lang not in SUPPORTED_LANGUAGES:
        lang = "en"
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=303)
    response.set_cookie("wbw_lang", lang, max_age=365 * 24 * 3600, samesite="lax")
    return response


app.include_router(public.router)
app.include_router(event_admin.router)
app.include_router(guest.router)
app.include_router(site_admin.router)
