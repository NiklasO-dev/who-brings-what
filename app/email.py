import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)


async def send_event_emails(
    to_email: str, title: str, admin_url: str, guest_url: str
) -> bool:
    if not settings.smtp_host:
        logger.warning("SMTP not configured, skipping email send")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"Your event: {title}"
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.set_content(
        f"Hello!\n\n"
        f'Your event "{title}" has been created.\n\n'
        f"Admin link (keep this private):\n{admin_url}\n\n"
        f"Guest link (share with participants):\n{guest_url}\n\n"
        f"Keep the admin link safe — it's the only way to manage your event.\n\n"
        f"Best regards,\nWho Brings What?"
    )

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            use_tls=settings.smtp_tls,
        )
        logger.info("Email sent to %s", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        return False
