from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import BringItem, Comment, Event, Participation, SiteStats
from app.templating import templates

router = APIRouter(prefix="/admin")

ADMIN_COOKIE_NAME = "wbw_admin_auth"
SESSION_MAX_AGE = 24 * 3600


def _get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.admin_password, salt="wbw-admin-session")


def is_authenticated(request: Request) -> bool:
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if not token:
        return False
    try:
        _get_serializer().loads(token, max_age=SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


async def run_cleanup(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    deleted_count = 0
    deleted_items = 0

    max_age_cutoff = now - timedelta(days=settings.event_max_age_days)
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.bring_items))
        .where(Event.done_at.is_(None), Event.created_at < max_age_cutoff)
    )
    to_delete = list(result.scalars().all())

    done_cutoff = now - timedelta(days=settings.done_event_cleanup_days)
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.bring_items))
        .where(Event.done_at.is_not(None), Event.done_at < done_cutoff)
    )
    to_delete += list(result.scalars().all())

    seen_ids: set[int] = set()
    unique_to_delete = []
    for event in to_delete:
        if event.id not in seen_ids:
            seen_ids.add(event.id)
            unique_to_delete.append(event)

    if unique_to_delete:
        result = await db.execute(select(SiteStats).where(SiteStats.id == 1))
        stats = result.scalar_one_or_none()
        if not stats:
            stats = SiteStats(id=1, removed_event_count=0, removed_bring_item_count=0)
            db.add(stats)

        for event in unique_to_delete:
            active_items = [i for i in event.bring_items if not i.is_removed]
            stats.removed_event_count += 1
            stats.removed_bring_item_count += len(active_items)
            deleted_items += len(active_items)
            await db.delete(event)
            deleted_count += 1

        await db.commit()

    return {"deleted_events": deleted_count, "deleted_items": deleted_items}


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "admin_login.html")


@router.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == settings.admin_password:
        token = _get_serializer().dumps("admin")
        response = RedirectResponse(url="/admin", status_code=303)
        response.set_cookie(
            ADMIN_COOKIE_NAME,
            token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return response
    return templates.TemplateResponse(
        request, "admin_login.html", {"error": True}, status_code=401
    )


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(ADMIN_COOKIE_NAME)
    return response


@router.get("")
async def site_admin_dashboard(
    request: Request, db: AsyncSession = Depends(get_db)
):
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    result = await db.execute(
        select(func.count()).select_from(Event).where(Event.done_at.is_(None))
    )
    active_events = result.scalar() or 0

    result = await db.execute(
        select(func.count()).select_from(Event).where(Event.done_at.is_not(None))
    )
    done_events_in_db = result.scalar() or 0

    result = await db.execute(select(SiteStats).where(SiteStats.id == 1))
    stats = result.scalar_one_or_none()
    removed_count = stats.removed_event_count if stats else 0
    total_done = done_events_in_db + removed_count

    result = await db.execute(
        select(func.count())
        .select_from(BringItem)
        .join(Event)
        .where(Event.done_at.is_(None), BringItem.removed_at.is_(None))
    )
    total_active_items = result.scalar() or 0

    avg_items = round(total_active_items / active_events, 1) if active_events > 0 else 0

    result = await db.execute(
        select(func.count())
        .select_from(Participation)
        .join(BringItem)
        .join(Event)
        .where(
            Event.done_at.is_(None),
            BringItem.removed_at.is_(None),
            Participation.removed_at.is_(None),
        )
    )
    total_participations = result.scalar() or 0

    result = await db.execute(
        select(func.count())
        .select_from(Comment)
        .join(BringItem)
        .join(Event)
        .where(
            Event.done_at.is_(None),
            BringItem.removed_at.is_(None),
            Comment.removed_at.is_(None),
        )
    )
    total_comments = result.scalar() or 0

    cleanup_result = request.query_params.get("cleanup")

    return templates.TemplateResponse(
        request,
        "site_admin.html",
        {
            "active_events": active_events,
            "done_events": total_done,
            "total_active_items": total_active_items,
            "avg_items": avg_items,
            "total_participations": total_participations,
            "total_comments": total_comments,
            "cleanup_result": cleanup_result,
            "settings": settings,
        },
    )


@router.post("/cleanup")
async def trigger_cleanup(request: Request, db: AsyncSession = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    result = await run_cleanup(db)
    deleted = result["deleted_events"]
    return RedirectResponse(url=f"/admin?cleanup={deleted}", status_code=303)
