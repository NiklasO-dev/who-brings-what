from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.encryption import verify_key
from app.models import BringItem, Comment, Event, Participation, SiteStats
from app.templating import templates
from app.event_crypto import (
    build_url,
    encrypt_bring_item_fields,
    encrypt_event_fields,
    get_key_from_request_or_form,
    redirect_with_key,
    require_key_and_decrypt,
)

router = APIRouter(prefix="/event/admin")


async def get_event_by_admin_token(admin_token: str, db: AsyncSession) -> Event | None:
    result = await db.execute(
        select(Event)
        .options(
            selectinload(Event.bring_items).selectinload(BringItem.participations),
            selectinload(Event.bring_items).selectinload(BringItem.comments),
        )
        .where(Event.admin_token == admin_token)
    )
    return result.scalar_one_or_none()


async def _require_valid_key(request: Request, event: Event) -> str | None:
    key = await get_key_from_request_or_form(request)
    if not key or not verify_key(key, event.encryption_key_hash):
        return None
    return key


@router.get("/{admin_token}")
async def admin_page(
    request: Request, admin_token: str, db: AsyncSession = Depends(get_db)
):
    event = await get_event_by_admin_token(admin_token, db)
    if not event:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": request.state.t.get("error_not_found", "Event not found.")},
            status_code=404,
        )

    key, error_response = await require_key_and_decrypt(
        request,
        event,
        action_url=f"/event/admin/{admin_token}/unlock",
        list_type="admin",
        reveal_token=admin_token,
    )
    if error_response:
        return error_response

    show_key_reveal = event.key_reveal_pending
    if show_key_reveal:
        event.key_reveal_pending = False
        event.key_reveal_wrapped = None
        await db.commit()

    guest_url_with_key = build_url(
        f"{settings.app_base_url}/event/guest", event.guest_token, key, True
    )
    guest_url_without_key = build_url(
        f"{settings.app_base_url}/event/guest", event.guest_token, key, False
    )
    admin_url_with_key = build_url(
        f"{settings.app_base_url}/event/admin", event.admin_token, key, True
    )
    admin_url_without_key = build_url(
        f"{settings.app_base_url}/event/admin", event.admin_token, key, False
    )

    expires_at = event.created_at + timedelta(days=settings.event_max_age_days)
    active_items = [i for i in event.bring_items if not i.is_removed]
    preset_items = [i for i in active_items if i.is_preset]
    guest_items = [i for i in active_items if not i.is_preset]

    return templates.TemplateResponse(
        request,
        "event_admin.html",
        {
            "event": event,
            "preset_items": preset_items,
            "guest_items": guest_items,
            "all_items": active_items,
            "guest_url_with_key": guest_url_with_key,
            "guest_url_without_key": guest_url_without_key,
            "admin_url_with_key": admin_url_with_key,
            "admin_url_without_key": admin_url_without_key,
            "encryption_key": key,
            "show_key_reveal": show_key_reveal,
            "expires_at": expires_at,
            "settings": settings,
        },
    )


@router.post("/{admin_token}/unlock")
async def unlock_admin(
    request: Request,
    admin_token: str,
    encryption_key: str = Form(...),
):
    key = encryption_key.strip()
    return redirect_with_key(f"/event/admin/{admin_token}", key)


@router.post("/{admin_token}/title")
async def update_title(
    request: Request,
    admin_token: str,
    title: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    event = await get_event_by_admin_token(admin_token, db)
    if not event:
        return RedirectResponse(url="/", status_code=303)

    key = await _require_valid_key(request, event)
    if not key:
        return RedirectResponse(url=f"/event/admin/{admin_token}", status_code=303)

    encrypt_event_fields(event, key, title=title.strip())
    await db.commit()
    return redirect_with_key(f"/event/admin/{admin_token}", key)


@router.post("/{admin_token}/presets")
async def add_preset(
    request: Request,
    admin_token: str,
    title: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    event = await get_event_by_admin_token(admin_token, db)
    if not event or event.is_done:
        return RedirectResponse(url="/", status_code=303)

    key = await _require_valid_key(request, event)
    if not key:
        return RedirectResponse(url=f"/event/admin/{admin_token}", status_code=303)

    preset_items = [i for i in event.bring_items if i.is_preset and not i.is_removed]
    max_pos = max((item.position for item in preset_items), default=-1)

    item = BringItem(event_id=event.id, source="preset", position=max_pos + 1)
    encrypt_bring_item_fields(
        item, key, title=title.strip(), description=description.strip() or None
    )
    db.add(item)
    await db.commit()
    return redirect_with_key(f"/event/admin/{admin_token}", key)


@router.post("/{admin_token}/presets/reorder")
async def reorder_presets(
    admin_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    event = await get_event_by_admin_token(admin_token, db)
    if not event or event.is_done:
        return RedirectResponse(url="/", status_code=303)

    key = await _require_valid_key(request, event)
    if not key:
        return RedirectResponse(url=f"/event/admin/{admin_token}", status_code=303)

    form_data = await request.form()
    order_raw = form_data.get("order", "")
    if not order_raw:
        return redirect_with_key(f"/event/admin/{admin_token}", key)

    try:
        item_ids = [int(x) for x in order_raw.split(",") if x.strip()]
    except ValueError:
        return redirect_with_key(f"/event/admin/{admin_token}", key)

    for position, item_id in enumerate(item_ids):
        result = await db.execute(
            select(BringItem).where(
                BringItem.id == item_id,
                BringItem.event_id == event.id,
                BringItem.source == "preset",
            )
        )
        item = result.scalar_one_or_none()
        if item:
            item.position = position

    await db.commit()
    return redirect_with_key(f"/event/admin/{admin_token}", key)


@router.post("/{admin_token}/presets/{item_id}/edit")
async def edit_preset(
    request: Request,
    admin_token: str,
    item_id: int,
    title: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    event = await get_event_by_admin_token(admin_token, db)
    if not event:
        return RedirectResponse(url="/", status_code=303)

    key = await _require_valid_key(request, event)
    if not key:
        return RedirectResponse(url=f"/event/admin/{admin_token}", status_code=303)

    result = await db.execute(
        select(BringItem).where(
            BringItem.id == item_id,
            BringItem.event_id == event.id,
            BringItem.source == "preset",
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        return redirect_with_key(f"/event/admin/{admin_token}", key)

    encrypt_bring_item_fields(
        item, key, title=title.strip(), description=description.strip() or None
    )
    await db.commit()
    return redirect_with_key(f"/event/admin/{admin_token}", key)


@router.post("/{admin_token}/presets/{item_id}/delete")
async def delete_preset(
    request: Request,
    admin_token: str,
    item_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await _delete_item(request, admin_token, item_id, db)


@router.post("/{admin_token}/items/{item_id}/delete")
async def delete_item(
    request: Request,
    admin_token: str,
    item_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await _delete_item(request, admin_token, item_id, db)


async def _delete_item(
    request: Request, admin_token: str, item_id: int, db: AsyncSession
):
    event = await get_event_by_admin_token(admin_token, db)
    if not event:
        return RedirectResponse(url="/", status_code=303)

    key = await _require_valid_key(request, event)
    if not key:
        return RedirectResponse(url=f"/event/admin/{admin_token}", status_code=303)

    result = await db.execute(
        select(BringItem).where(BringItem.id == item_id, BringItem.event_id == event.id)
    )
    item = result.scalar_one_or_none()
    if item:
        item.removed_at = datetime.now(timezone.utc)
        await db.commit()
    return redirect_with_key(f"/event/admin/{admin_token}", key)


@router.post("/{admin_token}/participations/{participation_id}/delete")
async def delete_participation(
    request: Request,
    admin_token: str,
    participation_id: int,
    db: AsyncSession = Depends(get_db),
):
    event = await get_event_by_admin_token(admin_token, db)
    if not event:
        return RedirectResponse(url="/", status_code=303)

    key = await _require_valid_key(request, event)
    if not key:
        return RedirectResponse(url=f"/event/admin/{admin_token}", status_code=303)

    result = await db.execute(
        select(Participation)
        .join(BringItem)
        .where(Participation.id == participation_id, BringItem.event_id == event.id)
    )
    participation = result.scalar_one_or_none()
    if participation:
        participation.removed_at = datetime.now(timezone.utc)
        await db.commit()
    return redirect_with_key(f"/event/admin/{admin_token}", key)


@router.post("/{admin_token}/comments/{comment_id}/delete")
async def delete_comment(
    request: Request,
    admin_token: str,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
):
    event = await get_event_by_admin_token(admin_token, db)
    if not event:
        return RedirectResponse(url="/", status_code=303)

    key = await _require_valid_key(request, event)
    if not key:
        return RedirectResponse(url=f"/event/admin/{admin_token}", status_code=303)

    result = await db.execute(
        select(Comment)
        .join(BringItem)
        .where(Comment.id == comment_id, BringItem.event_id == event.id)
    )
    comment = result.scalar_one_or_none()
    if comment:
        comment.removed_at = datetime.now(timezone.utc)
        await db.commit()
    return redirect_with_key(f"/event/admin/{admin_token}", key)


@router.post("/{admin_token}/done")
async def mark_done(
    request: Request,
    admin_token: str,
    db: AsyncSession = Depends(get_db),
):
    event = await get_event_by_admin_token(admin_token, db)
    if not event:
        return RedirectResponse(url="/", status_code=303)

    key = await _require_valid_key(request, event)
    if not key:
        return RedirectResponse(url=f"/event/admin/{admin_token}", status_code=303)

    event.done_at = datetime.now(timezone.utc)
    await db.commit()
    return redirect_with_key(f"/event/admin/{admin_token}", key)


@router.post("/{admin_token}/delete")
async def delete_event(admin_token: str, db: AsyncSession = Depends(get_db)):
    event = await get_event_by_admin_token(admin_token, db)
    if not event:
        return RedirectResponse(url="/", status_code=303)

    result = await db.execute(select(SiteStats).where(SiteStats.id == 1))
    stats = result.scalar_one_or_none()
    if not stats:
        stats = SiteStats(id=1, removed_event_count=0, removed_bring_item_count=0)
        db.add(stats)

    active_items = [i for i in event.bring_items if not i.is_removed]
    stats.removed_event_count += 1
    stats.removed_bring_item_count += len(active_items)

    await db.delete(event)
    await db.commit()
    return RedirectResponse(url="/?deleted=1", status_code=303)


@router.get("/{admin_token}/export")
async def export_event(
    request: Request, admin_token: str, db: AsyncSession = Depends(get_db)
):
    event = await get_event_by_admin_token(admin_token, db)
    if not event:
        return RedirectResponse(url="/", status_code=303)

    key, error_response = await require_key_and_decrypt(
        request,
        event,
        action_url=f"/event/admin/{admin_token}/unlock",
        list_type="admin",
        reveal_token=admin_token,
    )
    if error_response:
        return error_response

    active_items = [i for i in event.bring_items if not i.is_removed]
    export_date = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    return templates.TemplateResponse(
        request,
        "event_export.html",
        {
            "event": event,
            "items": active_items,
            "export_date": export_date,
            "encryption_key": key,
        },
    )


@router.get("/{admin_token}/share")
async def share_event(
    request: Request, admin_token: str, db: AsyncSession = Depends(get_db)
):
    event = await get_event_by_admin_token(admin_token, db)
    if not event:
        return RedirectResponse(url="/", status_code=303)

    key, error_response = await require_key_and_decrypt(
        request,
        event,
        action_url=f"/event/admin/{admin_token}/unlock",
        list_type="admin",
        reveal_token=admin_token,
    )
    if error_response:
        return error_response

    guest_url_with_key = build_url(
        f"{settings.app_base_url}/event/guest", event.guest_token, key, True
    )
    guest_url_without_key = build_url(
        f"{settings.app_base_url}/event/guest", event.guest_token, key, False
    )

    return templates.TemplateResponse(
        request,
        "event_share.html",
        {
            "event": event,
            "guest_url_with_key": guest_url_with_key,
            "guest_url_without_key": guest_url_without_key,
            "encryption_key": key,
            "event_description": None,
        },
    )
