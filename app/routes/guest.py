from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.encryption import verify_key
from app.models import BringItem, Comment, Event, Participation
from app.templating import templates
from app.event_crypto import (
    encrypt_bring_item_fields,
    encrypt_comment_fields,
    encrypt_participation_fields,
    get_key_from_request_or_form,
    redirect_with_key,
    require_key_and_decrypt,
    url_with_key,
)

router = APIRouter(prefix="/event/guest")


async def get_event_by_guest_token(guest_token: str, db: AsyncSession) -> Event | None:
    result = await db.execute(
        select(Event)
        .options(
            selectinload(Event.bring_items).selectinload(BringItem.participations),
            selectinload(Event.bring_items).selectinload(BringItem.comments),
        )
        .where(Event.guest_token == guest_token, Event.done_at.is_(None))
    )
    return result.scalar_one_or_none()


@router.get("/{guest_token}")
async def guest_page(
    request: Request, guest_token: str, db: AsyncSession = Depends(get_db)
):
    event = await get_event_by_guest_token(guest_token, db)
    if not event:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "message": request.state.t.get(
                    "error_unavailable", "This event is no longer available."
                )
            },
            status_code=404,
        )

    key, error_response = await require_key_and_decrypt(
        request,
        event,
        action_url=f"/event/guest/{guest_token}/unlock",
        list_type="guest",
    )
    if error_response:
        return error_response

    active_items = [i for i in event.bring_items if not i.is_removed]
    preset_items = [i for i in active_items if i.is_preset]
    guest_items = [i for i in active_items if not i.is_preset]

    return templates.TemplateResponse(
        request,
        "event_guest.html",
        {
            "event": event,
            "preset_items": preset_items,
            "guest_items": guest_items,
            "guest_token": guest_token,
            "encryption_key": key,
        },
    )


@router.post("/{guest_token}/unlock")
async def unlock_guest(
    guest_token: str,
    encryption_key: str = Form(...),
):
    key = encryption_key.strip()
    return redirect_with_key(f"/event/guest/{guest_token}", key)


@router.post("/{guest_token}/items")
async def add_item(
    request: Request,
    guest_token: str,
    title: str = Form(...),
    description: str = Form(""),
    person_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    event = await get_event_by_guest_token(guest_token, db)
    if not event:
        return RedirectResponse(url="/", status_code=303)

    key = await get_key_from_request_or_form(request)
    if not key or not verify_key(key, event.encryption_key_hash):
        return RedirectResponse(url=f"/event/guest/{guest_token}", status_code=303)

    guest_items = [i for i in event.bring_items if not i.is_preset and not i.is_removed]
    max_pos = max((item.position for item in guest_items), default=99)

    item = BringItem(event_id=event.id, source="guest", position=max_pos + 1)
    encrypt_bring_item_fields(
        item, key, title=title.strip(), description=description.strip() or None
    )
    db.add(item)
    await db.flush()

    participation = Participation(bring_item_id=item.id)
    encrypt_participation_fields(
        participation, key, person_name=person_name.strip(), note=None
    )
    db.add(participation)
    await db.commit()
    return redirect_with_key(f"/event/guest/{guest_token}", key)


@router.post("/{guest_token}/items/{item_id}/participate")
async def participate(
    request: Request,
    guest_token: str,
    item_id: int,
    person_name: str = Form(...),
    note: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    event = await get_event_by_guest_token(guest_token, db)
    if not event:
        return RedirectResponse(url="/", status_code=303)

    key = await get_key_from_request_or_form(request)
    if not key or not verify_key(key, event.encryption_key_hash):
        return RedirectResponse(url=f"/event/guest/{guest_token}", status_code=303)

    result = await db.execute(
        select(BringItem).where(
            BringItem.id == item_id,
            BringItem.event_id == event.id,
            BringItem.removed_at.is_(None),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        return redirect_with_key(f"/event/guest/{guest_token}", key)

    participation = Participation(bring_item_id=item.id)
    encrypt_participation_fields(
        participation,
        key,
        person_name=person_name.strip(),
        note=note.strip() or None,
    )
    db.add(participation)
    await db.commit()
    await db.refresh(participation)

    redirect_url = url_with_key(f"/event/guest/{guest_token}", key)
    return JSONResponse(
        content={"participation_id": participation.id, "redirect": redirect_url},
        status_code=200,
    )


@router.post("/{guest_token}/participations/{participation_id}/undo")
async def undo_participation(
    request: Request,
    guest_token: str,
    participation_id: int,
    db: AsyncSession = Depends(get_db),
):
    event = await get_event_by_guest_token(guest_token, db)
    if not event:
        return JSONResponse(content={"error": "not_found"}, status_code=404)

    key = await get_key_from_request_or_form(request)
    if not key or not verify_key(key, event.encryption_key_hash):
        return JSONResponse(content={"error": "not_found"}, status_code=404)

    result = await db.execute(
        select(Participation)
        .join(BringItem)
        .where(
            Participation.id == participation_id,
            BringItem.event_id == event.id,
            Participation.removed_at.is_(None),
        )
    )
    participation = result.scalar_one_or_none()
    if not participation:
        return JSONResponse(content={"error": "not_found"}, status_code=404)

    now = datetime.now(timezone.utc)
    created = participation.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if (now - created).total_seconds() > 60:
        return JSONResponse(content={"error": "expired"}, status_code=410)

    participation.removed_at = now
    await db.commit()
    return JSONResponse(content={"success": True}, status_code=200)


@router.post("/{guest_token}/items/{item_id}/comments")
async def add_comment(
    request: Request,
    guest_token: str,
    item_id: int,
    author_name: str = Form(...),
    text: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    event = await get_event_by_guest_token(guest_token, db)
    if not event:
        return RedirectResponse(url="/", status_code=303)

    key = await get_key_from_request_or_form(request)
    if not key or not verify_key(key, event.encryption_key_hash):
        return RedirectResponse(url=f"/event/guest/{guest_token}", status_code=303)

    result = await db.execute(
        select(BringItem).where(
            BringItem.id == item_id,
            BringItem.event_id == event.id,
            BringItem.removed_at.is_(None),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        return redirect_with_key(f"/event/guest/{guest_token}", key)

    comment = Comment(bring_item_id=item.id)
    encrypt_comment_fields(comment, key, author_name=author_name.strip(), text=text.strip())
    db.add(comment)
    await db.commit()
    return redirect_with_key(f"/event/guest/{guest_token}", key)
