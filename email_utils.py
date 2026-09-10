"""
Email delivery + signed-token helpers for email verification and password reset.

Email sending:
- If SMTP is configured via environment variables (MAIL_SERVER, MAIL_USERNAME,
  MAIL_PASSWORD, MAIL_DEFAULT_SENDER), real emails are sent over SMTP.
- If it isn't configured, the message is logged to the console instead, and the
  caller can fall back to showing the link directly in the UI (see the
  `dev_preview_link` flash used in app.py) so the whole flow is testable without
  a real mail server.

Tokens:
- Built with itsdangerous' URLSafeTimedSerializer, salted per purpose, so a
  verification token can't be replayed as a password-reset token.
- No token table needed; validity is purely a function of the signature + age.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app, url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

VERIFY_SALT = "email-verify"
RESET_SALT = "password-reset"

VERIFY_MAX_AGE = 60 * 60 * 24  # 24 hours
RESET_MAX_AGE = 60 * 60  # 1 hour


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_token(email: str, salt: str) -> str:
    return _serializer().dumps(email, salt=salt)


def confirm_token(token: str, salt: str, max_age: int):
    """Returns the email the token was issued for, or None if invalid/expired."""
    try:
        return _serializer().loads(token, salt=salt, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def smtp_configured() -> bool:
    return bool(os.environ.get("MAIL_SERVER") and os.environ.get("MAIL_DEFAULT_SENDER"))


def send_email(subject: str, recipient: str, body: str) -> bool:
    """Sends a plain-text email. Returns True if it went out over real SMTP,
    False if it was only logged (dev mode)."""
    if not smtp_configured():
        current_app.logger.info(
            "[dev email — SMTP not configured]\nTo: %s\nSubject: %s\n\n%s",
            recipient, subject, body,
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ["MAIL_DEFAULT_SENDER"]
    msg["To"] = recipient
    msg.set_content(body)

    host = os.environ["MAIL_SERVER"]
    port = int(os.environ.get("MAIL_PORT", 587))
    username = os.environ.get("MAIL_USERNAME")
    password = os.environ.get("MAIL_PASSWORD")
    use_tls = os.environ.get("MAIL_USE_TLS", "true").lower() != "false"

    with smtplib.SMTP(host, port) as server:
        if use_tls:
            server.starttls(context=ssl.create_default_context())
        if username and password:
            server.login(username, password)
        server.send_message(msg)
    return True


def send_verification_email(user) -> tuple[bool, str]:
    token = generate_token(user.email, VERIFY_SALT)
    link = url_for("verify_email", token=token, _external=True)
    body = (
        f"Hi {user.name},\n\n"
        f"Confirm your email for Daily Check-in by opening this link "
        f"(it expires in 24 hours):\n\n{link}\n\n"
        f"If you didn't create this account, you can ignore this email."
    )
    sent = send_email("Confirm your email — Daily Check-in", user.email, body)
    return sent, link


def send_password_reset_email(user) -> tuple[bool, str]:
    token = generate_token(user.email, RESET_SALT)
    link = url_for("reset_password", token=token, _external=True)
    body = (
        f"Hi {user.name},\n\n"
        f"We received a request to reset your Daily Check-in password. "
        f"This link expires in 1 hour:\n\n{link}\n\n"
        f"If you didn't request this, you can safely ignore this email — "
        f"your password won't change."
    )
    sent = send_email("Reset your password — Daily Check-in", user.email, body)
    return sent, link
