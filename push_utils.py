"""
Web Push notifications via VAPID, using pywebpush.

Configuration (all required for push to actually send):
  VAPID_PUBLIC_KEY   - base64url-encoded public key
  VAPID_PRIVATE_KEY  - base64url-encoded private key (or PEM, pywebpush accepts either)
  VAPID_CLAIMS_EMAIL - contact email, e.g. "mailto:you@example.com"

Generate a keypair with `python generate_vapid_keys.py`.

If unconfigured, push_configured() is False, the "Enable push notifications"
control in Account settings stays hidden, and send_push() is a no-op.
"""

import os
import json

from flask import current_app

try:
    from pywebpush import webpush, WebPushException
except ImportError:  # pragma: no cover - only hit if pywebpush isn't installed
    webpush = None
    WebPushException = Exception


def push_configured() -> bool:
    return bool(
        os.environ.get("VAPID_PUBLIC_KEY")
        and os.environ.get("VAPID_PRIVATE_KEY")
        and os.environ.get("VAPID_CLAIMS_EMAIL")
    )


def vapid_public_key():
    return os.environ.get("VAPID_PUBLIC_KEY")


def send_push(subscription_info: dict, title: str, body: str, url: str = "/") -> bool:
    """Sends one push notification. Returns True on success, False otherwise
    (including when push isn't configured). Never raises — a bad/expired
    subscription shouldn't take down the caller's loop over many users."""
    if not push_configured() or webpush is None:
        return False

    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
            vapid_claims={"sub": os.environ["VAPID_CLAIMS_EMAIL"]},
        )
        return True
    except WebPushException as e:
        current_app.logger.warning("Push send failed: %s", e)
        return False
    except Exception as e:  # noqa: BLE001 - log and move on, never crash the sender
        current_app.logger.warning("Push send error: %s", e)
        return False
