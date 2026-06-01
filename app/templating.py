from urllib.parse import urlparse

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import settings


def domain_from_url(url: str) -> str:
    """Extract domain name from a URL, stripping www. prefix."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or url
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return url


class I18nTemplates(Jinja2Templates):
    """Custom Jinja2Templates that automatically injects i18n context."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.env.filters["domain"] = domain_from_url

    def TemplateResponse(self, request: Request, name: str, context: dict | None = None, **kwargs):
        if context is None:
            context = {}
        # Inject translation context from request state
        if hasattr(request.state, "t"):
            context.setdefault("t", request.state.t)
        if hasattr(request.state, "lang"):
            context.setdefault("lang", request.state.lang)
        context.setdefault("settings", settings)
        return super().TemplateResponse(request, name, context, **kwargs)


templates = I18nTemplates(directory="app/templates")
