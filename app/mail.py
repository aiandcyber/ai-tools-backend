import re
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from app import config

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def looks_real_email(value: str) -> bool:
    text = (value or "").strip()
    if not _EMAIL_RE.match(text):
        return False
    domain = text.rsplit("@", 1)[1].lower()
    if domain in {"example.com", "test.com", "localhost", "invalid", "mailinator.com"}:
        return False
    return _has_mail_domain(domain)


def _has_mail_domain(domain: str) -> bool:
    for qtype in ("MX", "A"):
        try:
            response = httpx.get(
                "https://cloudflare-dns.com/dns-query",
                params={"name": domain, "type": qtype},
                headers={"accept": "application/dns-json"},
                timeout=8,
            )
            answers = response.json().get("Answer") or []
            if any(item.get("data") for item in answers):
                return True
        except Exception:
            continue
    return False


def send_feedback(user_email: str, youtube_url: str, message: str) -> None:
    email = (user_email or "").strip()
    if not looks_real_email(email):
        raise ValueError("Please enter a real email address")
    report = (
        f"From: {email}\n"
        f"YouTube link: {(youtube_url or '').strip() or '(none)'}\n\n"
        f"{(message or '').strip()}"
    )
    # Send to the user first. If that address is dead, do not send to contact@.
    _deliver(
        to=email,
        subject="We received your YouTube tools report",
        body=f"Thanks. We received this report:\n\n{report}",
        reply_to=config.FEEDBACK_TO,
    )
    _deliver(
        to=config.FEEDBACK_TO,
        subject="YouTube tool report",
        body=report,
        reply_to=email,
    )


def _deliver(to: str, subject: str, body: str, reply_to: str) -> None:
    if config.SMTP_HOST:
        _smtp_send(to, subject, body, reply_to)
        return
    if config.CF_ACCOUNT_ID and config.CF_EMAIL_API_TOKEN:
        _cloudflare_send(to, subject, body, reply_to)
        return
    raise RuntimeError("Email sending is not configured")


def _smtp_send(to: str, subject: str, body: str, reply_to: str) -> None:
    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = reply_to
    msg.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as smtp:
        smtp.starttls(context=context)
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)


def _cloudflare_send(to: str, subject: str, body: str, reply_to: str) -> None:
    response = httpx.post(
        f"https://api.cloudflare.com/client/v4/accounts/{config.CF_ACCOUNT_ID}/email/sending/send",
        headers={
            "Authorization": f"Bearer {config.CF_EMAIL_API_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "to": to,
            "from": {"address": config.SMTP_FROM, "name": "AI-for All Tools"},
            "reply_to": reply_to,
            "subject": subject,
            "text": body,
        },
        timeout=20,
    )
    payload = response.json() if response.content else {}
    result = payload.get("result") or {}
    bounces = result.get("permanent_bounces") or []
    if response.status_code >= 400 or not payload.get("success", True):
        raise RuntimeError("Could not send email")
    if any(str(item).lower() == to.lower() for item in bounces):
        raise RuntimeError("Email address is not working")
