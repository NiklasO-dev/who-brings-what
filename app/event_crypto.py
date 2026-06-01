from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.encryption import decrypt, decrypt_optional, encrypt, encrypt_optional, verify_key
from app.models import BringItem, Comment, Event, Participation
from app.templating import templates


def decrypt_event(event: Event, key: str) -> None:
    event.title = decrypt(event.title, key)
    event.organizer_email = decrypt_optional(event.organizer_email, key)
    for item in event.bring_items:
        decrypt_bring_item(item, key)


def decrypt_bring_item(item: BringItem, key: str) -> None:
    item.title = decrypt(item.title, key)
    item.description = decrypt_optional(item.description, key)
    for participation in item.participations:
        decrypt_participation(participation, key)
    for comment in item.comments:
        decrypt_comment(comment, key)


def decrypt_participation(participation: Participation, key: str) -> None:
    participation.person_name = decrypt(participation.person_name, key)
    participation.note = decrypt_optional(participation.note, key)


def decrypt_comment(comment: Comment, key: str) -> None:
    comment.author_name = decrypt(comment.author_name, key)
    comment.text = decrypt(comment.text, key)


def encrypt_event_fields(
    event: Event, key: str, *, title: str | None = None, organizer_email: str | None = None
) -> None:
    if title is not None:
        event.title = encrypt(title, key)
    if organizer_email is not None:
        event.organizer_email = encrypt_optional(organizer_email, key)


def encrypt_bring_item_fields(
    item: BringItem,
    key: str,
    *,
    title: str,
    description: str | None = None,
) -> None:
    item.title = encrypt(title, key)
    item.description = encrypt_optional(description, key)


def encrypt_participation_fields(
    participation: Participation,
    key: str,
    *,
    person_name: str,
    note: str | None = None,
) -> None:
    participation.person_name = encrypt(person_name, key)
    participation.note = encrypt_optional(note, key)


def encrypt_comment_fields(
    comment: Comment,
    key: str,
    *,
    author_name: str,
    text: str,
) -> None:
    comment.author_name = encrypt(author_name, key)
    comment.text = encrypt(text, key)


def build_url(base_path: str, token: str, key: str | None = None, include_key: bool = True) -> str:
    path = f"{base_path}/{token}"
    if include_key and key:
        return f"{path}?{urlencode({'key': key})}"
    return path


def url_with_key(path: str, key: str) -> str:
    return f"{path}?{urlencode({'key': key})}"


def redirect_with_key(path: str, key: str) -> RedirectResponse:
    separator = "&" if "?" in path else "?"
    return RedirectResponse(url=f"{path}{separator}{urlencode({'key': key})}", status_code=303)


def get_key_from_request(request: Request) -> str | None:
    key = request.query_params.get("key")
    if key:
        return key.strip()
    return None


async def get_key_from_request_or_form(request: Request) -> str | None:
    key = get_key_from_request(request)
    if key:
        return key
    if request.method == "POST":
        form = await request.form()
        raw = form.get("key")
        if raw:
            return str(raw).strip()
    return None


def render_unlock_page(
    request: Request,
    *,
    action_url: str,
    list_type: str,
    error: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "unlock.html",
        {
            "action_url": action_url,
            "list_type": list_type,
            "error": error,
        },
        status_code=401 if error else 200,
    )


async def require_key_and_decrypt(
    request: Request,
    event: Event,
    *,
    action_url: str,
    list_type: str,
    reveal_token: str | None = None,
) -> tuple[str | None, object | None]:
    if event.key_reveal_pending and event.key_reveal_wrapped and reveal_token:
        try:
            key = decrypt(event.key_reveal_wrapped, reveal_token)
            if verify_key(key, event.encryption_key_hash):
                decrypt_event(event, key)
                return key, None
        except Exception:
            pass

    key = await get_key_from_request_or_form(request)
    if not key:
        return None, render_unlock_page(request, action_url=action_url, list_type=list_type)
    if not verify_key(key, event.encryption_key_hash):
        return None, render_unlock_page(
            request,
            action_url=action_url,
            list_type=list_type,
            error=request.state.t.get("unlock_error_invalid", "Invalid encryption key."),
        )
    try:
        decrypt_event(event, key)
    except Exception:
        return None, render_unlock_page(
            request,
            action_url=action_url,
            list_type=list_type,
            error=request.state.t.get("unlock_error_invalid", "Invalid encryption key."),
        )
    return key, None
