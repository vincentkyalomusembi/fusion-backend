import base64

from app.config import settings
from brevo import Brevo
from brevo.transactional_emails import (
    SendTransacEmailRequestAttachmentItem,
    SendTransacEmailRequestSender,
    SendTransacEmailRequestToItem,
)


def send_portfolio_csv(to_email: str, portfolio_name: str, filename: str, csv_bytes: bytes) -> str | None:
    if not settings.brevo_api_key:
        raise RuntimeError("BREVO_API_KEY is not configured")
    if not settings.brevo_sender_email:
        raise RuntimeError("BREVO_SENDER_EMAIL is not configured")

    client = Brevo(api_key=settings.brevo_api_key, timeout=30.0)
    response = client.transactional_emails.send_transac_email(
        sender=SendTransacEmailRequestSender(
            email=settings.brevo_sender_email,
            name=settings.brevo_sender_name,
        ),
        to=[SendTransacEmailRequestToItem(email=to_email)],
        subject=f"Your approved portfolio: {portfolio_name}",
        text_content=f"Attached is the approved exposure and hazard data for {portfolio_name}.",
        attachment=[SendTransacEmailRequestAttachmentItem(
            name=filename,
            content=base64.b64encode(csv_bytes).decode("ascii"),
        )],
    )
    return response.message_id
